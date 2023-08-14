# Boilerplate
import sys

sys.path.append("../../")

import pandas as pd
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

# Flask SQLAlchemy - import other tables


def call_reddit_table():
    """ """
    # Defining the SQLAlchemy-query
    currency_query = db.query(Currency).with_entities(Currency.id, Currency.name)

    # Getting all the entries via SQLAlchemy
    currency_query.all()

    pass


SQLALCHEMY_DATABASE_URI = "postgresql://postgres:postgres@localhost:5432/my_database"
engine = create_engine(SQLALCHEMY_DATABASE_URI, pool_pre_ping=True, echo=False)
db = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base(bind=engine)


class Currency(Base):
    """The `Currency`-table"""

    __tablename__ = "currency"
    __table_args__ = {"schema": "data"}

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(64), nullable=False)


# Defining the SQLAlchemy-query
currency_query = db.query(Currency).with_entities(Currency.id, Currency.name)

# Getting all the entries via SQLAlchemy
currencies = currency_query.all()

# We provide also the (alternate) column names and set the index here,
# renaming the column `id` to `currency__id`
df_from_records = pd.DataFrame.from_records(
    currencies, index="currency__id", columns=["currency__id", "name"]
)
print(df_from_records.head(5))

# Or getting the entries via Pandas instead of SQLAlchemy using the
# aforementioned function `read_sql_query()`. We can set the index-columns here as well
df_from_query = pd.read_sql_query(currency_query.statement, db.bind, index_col="id")
# Renaming the index-column(s) from `id` to `currency__id` needs another statement
df_from_query.index.rename(name="currency__id", inplace=True)
print(df_from_query.head(5))
