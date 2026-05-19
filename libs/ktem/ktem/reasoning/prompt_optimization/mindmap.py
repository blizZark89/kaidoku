import logging
import re
from textwrap import dedent

from ktem.llms.manager import llms

from kotaemon.base import BaseComponent, Document, HumanMessage, Node, SystemMessage
from kotaemon.llms import ChatLLM, PromptTemplate

logger = logging.getLogger(__name__)


MINDMAP_HTML_EXPORT_TEMPLATE = dedent(
    """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mindmap</title>
    <style>
      svg.markmap {
        width: 100%;
        height: 100vh;
      }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.16"></script>
  </head>
  <body>
    {markmap_div}
  </body>
</html>
"""
)


class CreateMindmapPipeline(BaseComponent):
    """Create a mindmap from the question and context"""

    llm: ChatLLM = Node(default_callback=lambda _: llms.get_default())

    SYSTEM_PROMPT = """
From now on you will behave as "MapGPT" and, for every text the user will submit, you are going to create a PlantUML mind map file for the inputted text to best describe main ideas. Format it as a code and remember that the mind map should be in the same language as the inputted context. You don't have to provide a general example for the mind map format before the user inputs the text.
    """  # noqa: E501
    MINDMAP_PROMPT_TEMPLATE = """
Question:
{question}

Context:
{context}

Generate a sample PlantUML mindmap for based on the provided question and context above. Only includes context relevant to the question to produce the mindmap.

IMPORTANT: For each non-root node that refers to content from a specific source document, append PDF and the page number at the end of the node label using this format: [PDF:page_number]
For example: "*** Access Control [PDF:12]"
The Context above already contains source information like "Content from filename.pdf (Page X)". Use that information to find the correct page number for each node. Do NOT include the document filename — only write [PDF:X].

Use the template like this:

@startmindmap
* Title
** Item A [PDF:3]
*** Item B [PDF:3]
**** Item C [PDF:7]
*** Item D [PDF:5]
@endmindmap
    """  # noqa: E501
    prompt_template: str = MINDMAP_PROMPT_TEMPLATE

    @classmethod
    def convert_uml_to_markdown(cls, text: str) -> str:
        start_phrase = "@startmindmap"
        end_phrase = "@endmindmap"

        try:
            text = text.split(start_phrase)[-1]
            text = text.split(end_phrase)[0]
            text = text.strip().replace("*", "#")
        except IndexError:
            text = ""

        return text

    @classmethod
    def extract_source_refs_from_markdown(
        cls, markdown_text: str
    ) -> dict[str, list[tuple[str, str]]]:
        """Extract source file + page references from mindmap nodes.

        Returns a dict mapping node text (without source annotation) to
        list of (filename, page) tuples.
        """
        refs: dict[str, list[tuple[str, str]]] = {}
        pattern = re.compile(r"\[PDF\s*:\s*(\d+)\]", re.IGNORECASE)

        for line in markdown_text.split("\n"):
            match = pattern.search(line)
            if match:
                filename = match.group(1).strip()
                page = match.group(2).strip()
                # Get node label without the source annotation
                clean_line = pattern.sub("", line).strip()
                node_text = clean_line.lstrip("#").strip()
                if node_text:
                    refs.setdefault(node_text, []).append((filename, page))

        return refs

    def run(self, question: str, context: str) -> Document:  # type: ignore
        prompt_template = PromptTemplate(self.prompt_template)
        prompt = prompt_template.populate(
            question=question,
            context=context,
        )

        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        uml_text = self.llm(messages).text
        markdown_text = self.convert_uml_to_markdown(uml_text)

        return Document(
            text=markdown_text,
        )