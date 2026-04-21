import logging

from ktem.llms.manager import llms

from kotaemon.base import AIMessage, BaseComponent, Document, HumanMessage, Node
from kotaemon.llms import ChatLLM, PromptTemplate

logger = logging.getLogger(__name__)


class SuggestConvNamePipeline(BaseComponent):
    """Suggest a good conversation name based on the chat history."""

    llm: ChatLLM = Node(default_callback=lambda _: llms.get_default())
    SUGGEST_NAME_PROMPT_TEMPLATE = (
        "Du bist Experte fuer praegnante und gut merkbare Unterhaltungstitel. "
        "Schlage auf Basis des bisherigen Chatverlaufs einen passenden Titel "
        "mit maximal 10 Woertern vor. "
        "Gib die Antwort auf {lang}. "
        "Antworte nur mit dem Titel ohne Zusatztext."
    )
    prompt_template: str = SUGGEST_NAME_PROMPT_TEMPLATE
    lang: str = "Deutsch"

    def run(self, chat_history: list[tuple[str, str]]) -> Document:  # type: ignore
        prompt_template = PromptTemplate(self.prompt_template)
        prompt = prompt_template.populate(lang=self.lang)

        messages = []
        for human, ai in chat_history:
            messages.append(HumanMessage(content=human))
            messages.append(AIMessage(content=ai))

        messages.append(HumanMessage(content=prompt))

        return self.llm(messages)
