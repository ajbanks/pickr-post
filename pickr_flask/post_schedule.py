import logging
from typing import List

from sqlalchemy import exc, insert

from .models import (
    db,
    PostSchedule,
    ModeledTopic
)

TOPIC_TEXT_SUFFIX = """
The posts in the scehdule are able to be edited or posted at a different time by clicking on the Edit and Schedule button.

Go ahead and edit the posts in the schedule if they are not quite to your liking!
"""


def create_schedule_text(topics: List[ModeledTopic]):
    return None


def create_schedule_text_no_trends(topics: List[ModeledTopic]):

    text = """Your post schedule for the week is below. We recommend you talk about the following topics this week\n"""
    
    for topic in topics:
        text += f"• {topic.name}\n"
    text += "\n"
    
    text += f"""All {len(topics)} topics are what we call evergreen topics. They are recently popular topics that always perform well when you post about them consistently enough\n\n"""
    
    return text + TOPIC_TEXT_SUFFIX


def create_schedule_text_only_trends(topics: List[ModeledTopic]):
    return None


def write_schedule(schedule: List[dict]):
    record = PostSchedule(**schedule)
    try:
        db.session.add(record)
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Error writing schedule post: {e}")
    else:
        db.session.commit()
