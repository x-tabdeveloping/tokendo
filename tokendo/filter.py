import random
from collections import Counter
from typing import Iterable, Optional, Union

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


class TokenFilter(TransformerMixin, BaseEstimator):
    """Sklearn component that filters out certain tokens given some attributes
    of them. Texts that are passed to the component have to be sentencized and
    tokenized already.
    All parameters are optional, if nothing is passed into the constructor
    it will act as the identity.

    Parameters
    ----------
    negative: iterable of str, default ()
        Tokens to remove, could be stop words or anyhting of
        the kind.
    length_range: tuple, default (0, None)
        A tuple of the lower and upper boundary on token length.
        If an integer it will be interpreted as absolute character count.
        If a float it will be interpreted as a quantile, and will be learned
        from data using reservoir sampling.
    frequency_range: tuple of (float, float), default (0.0, 1.0)
        Tuple of lower and upper frequency values.
        Frequency is learned from the data and is determined on the document
        level.
    max_features: int, default None
        Maximum number of unqique tokens to pass down the pipeline.
        If None, all tokens are allowed to pass.
    max_memory: int, default 5000
        Maximum size of the reservoir sampled token length pool.
        This is what the lenght quantiles are calculated from.
        Lower number means worse estimate, but lower memory usage.
    """

    def __init__(
        self,
        negative: Iterable[str] = (),
        length_range: tuple[Union[int, float], Union[int, float, None]] = (
            0,
            None,
        ),
        frequency_range: tuple[float, float] = (0.0, 1.0),
        max_features: Optional[int] = None,
        max_memory: int = 5000,
    ):
        self.negative = set(negative)
        self.length_range = length_range
        self.frequency_range = frequency_range
        self.minl, self.maxl = length_range
        if isinstance(self.minl, int):
            self.min_length_quantile = False
            self.min_length = self.minl
        elif isinstance(self.minl, float):
            self.min_length_quantile = True
            self.min_length = 0
        else:
            raise ValueError("Minimum length either has to be float or int.")
        if isinstance(self.maxl, int):
            self.max_length_quantile = False
            self.max_length = self.maxl
        elif isinstance(self.maxl, float):
            self.max_length_quantile = True
            self.max_length = None
        elif self.maxl is None:
            self.max_length_quantile = False
            self.max_length = None
        else:
            raise ValueError("Minimum length either has to be float or int.")
        self.length_pool = []
        self.seen_lengths = 0
        self.max_memory = max_memory
        self.frequencies = Counter()
        self.max_features = max_features
        self.most_common = None

    def append_reservoir(self, token: str):
        """Adds token length to the pool with reservoir sampling."""
        if self.seen_lengths < self.max_memory:
            self.length_pool.append(len(token))
        else:
            j = random.randint(0, self.seen_lengths)
            if j < self.max_memory:
                self.length_pool[j] = len(token)
        self.seen_lengths += 1

    def fit(self, X: list[list[str]], y=None):
        """Fits filter to the data.

        Parameters
        ----------
        X: list of list of str
            Tokens in documents.

        Returns
        -------
        self
        """
        return self.partial_fit(X, y)

    def partial_fit(self, X: list[list[str]], y=None):
        """Online fits filter to the data.

        Parameters
        ----------
        X: list of list of str
            Tokenized documents.

        Returns
        -------
        self
        """
        tokens = []
        for doc in X:
            for token in doc:
                tokens.append(token)
                self.append_reservoir(token)
        if self.max_length_quantile:
            self.max_length = np.quantile(self.length_pool, self.maxl)  # type: ignore
        if self.min_length_quantile:
            self.min_length = np.quantile(self.length_pool, self.minl)  # type: ignore
        self.frequencies.update(tokens)
        if self.max_features is not None:
            most_common_tokens = [
                token
                for token, _ in self.frequencies.most_common(self.max_features)
            ]
            self.most_common = set(most_common_tokens)
        return self

    def passes(self, token: str) -> bool:
        """Determines whether a token passes the filter or not."""
        token_length = len(token)
        total_freq = self.frequencies.total()
        token_frequency = 0
        if total_freq:
            token_frequency = self.frequencies.get(token, 0) / total_freq
        max_pass: bool = (self.max_length is None) or (
            token_length <= self.max_length
        )
        min_pass: bool = token_length >= self.min_length  # type: ignore
        freq_pass: bool = (token_frequency >= self.frequency_range[0]) and (
            token_frequency <= self.frequency_range[1]
        )
        is_in_most_common = (self.most_common is None) or (
            token in self.most_common
        )
        return (
            (token not in self.negative)
            and max_pass
            and min_pass
            and freq_pass
            and is_in_most_common
        )

    def transform(self, X: list[list[str]]) -> list[list[str]]:
        """Filters out tokens that do not pass based on the provided
        set of rules.

        Parameters
        ----------
        X: list of list of str
            Tokenized documents.

        Returns
        -------
        list of list of str
            Documents with the problematic tokens removed.
        """
        res = []
        for doc in X:
            res_tokens = [token for token in doc if self.passes(token)]
            res.append(res_tokens)
        return res

    def get_feature_names_out(self, input_features=None):
        return None
