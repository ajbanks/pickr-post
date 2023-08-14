# Pydantic library
from pydantic import BaseModel, model_validator


class PickrValidation(BaseModel):
    id: int
    username: str
    created_at: str
    text: str
    reply_count: int
    quote_count: int
    retweets: int
    likes: int
    followers_count: int
    url: str
    clean_text: str

    @model_validator(mode="before")
    def _remove_non_ints(cls, values):
        """ """
        fields = [
            "id",
            "followers_count",
            "likes",
            "reply_count",
            "quote_count",
            "retweets",
        ]
        for field in fields:
            if not isinstance(values.get(field), int):
                values[field] = int(values[field])
        return values
