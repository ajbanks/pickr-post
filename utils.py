import re

from funcy import rcompose, lfilter, lmap, complement, partial
from langdetect import detect
from nltk.tokenize import TweetTokenizer
from emoji import is_emoji

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


def create_hashtag_from_string(term: str) -> str:
    return "#" + term.replace(" ", "")


def lang(text):
    try:
        return detect(text)
    except:
        return "na"
