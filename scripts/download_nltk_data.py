"""Download NLTK data required by unstructured for PPTX/DOCX parsing."""
import nltk

NLTK_DATA = "/usr/local/share/nltk_data"
PACKAGES = ("punkt_tab", "averaged_perceptron_tagger_eng", "stopwords")

for pkg in PACKAGES:
    nltk.download(pkg, download_dir=NLTK_DATA, quiet=True)
    print(f"NLTK {pkg}: downloaded")