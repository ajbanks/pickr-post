import re
from typing import List

import nltk
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from funcy import rcompose, lfilter, lmap, complement, partial
from nltk.tokenize import TweetTokenizer
from bs4 import BeautifulSoup
from emoji import is_emoji

nltk.download('punkt')
nltk.download('stopwords')

tweet_tokenizer = TweetTokenizer(
    preserve_case=False, reduce_len=True, strip_handles=True
)
remove_emojis = partial(lfilter, complement(is_emoji))
strip_hashtags = partial(lmap, lambda w: w.lstrip("#"))
normalise_tweet = rcompose(
    lambda t: re.sub(r"http\S+", "", t),
    lambda t: re.sub(r"^RT @\S+:\s+", "", t),
    tweet_tokenizer.tokenize,
    remove_emojis,
    strip_hashtags,
    lambda ts: " ".join(ts),
)


def parse_html(text):
    return BeautifulSoup(text, "html.parser").get_text()


def remove_stop_words(docs: List[str]):
    """Remove stop words form a list of documents"""
    stop_words = get_stop_words()
    lemmatizer = WordNetLemmatizer()
    docs_non_sw = []
    for d in docs:
        non_stop_title = " ".join(
            [
                lemmatizer.lemmatize(word).lower()
                for word in word_tokenize(d)
                if word not in stop_words and word.strip != "" and len(word) > 1
            ]
        )
        non_stop_title = re.sub("[^a-zA-Z0-9 \n\.]", "", non_stop_title)
        non_stop_title = set(word_tokenize(non_stop_title))
        docs_non_sw.append(non_stop_title)
    return docs_non_sw


def get_stop_words():
    stop_words = set(stopwords.words('english'))
    stop_words.add('what')
    stop_words.add('when')
    stop_words.add('who')
    stop_words.add('where')
    stop_words.add('how')
    stop_words.add('is')
    stop_words.add('an')
    return stop_words