from sentence_transformers import SentenceTransformer, util
import numpy as np
from typing import List, Tuple, Dict


class TextEmbedder():

    def __init__(self):
        self.embedding_model = SentenceTransformer('multi-qa-MiniLM-L6-cos-v1')


    def embed(self, str_or_list) -> np.array:
        """converts text in to a sentence embedding representation"""
        text_embeddings = self.embedding_model.encode(str_or_list)
        return text_embeddings

    def get_embedding_comparison_list(self, topic_strings):
        # Compute cosine-similarities
        topic_embeddings = self.embed(topic_strings)
        cosine_scores = util.cos_sim(topic_embeddings, topic_embeddings)
        return cosine_scores

    def embedding_simimalrity(self, embeddings1, embeddings2):
        # Compute cosine-similarities
        cosine_scores = util.cos_sim([embeddings1], [embeddings2])
        return cosine_scores