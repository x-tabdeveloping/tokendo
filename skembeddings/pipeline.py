import tempfile
from pathlib import Path
from typing import Union

from confection import Config, registry
from huggingface_hub import HfApi, snapshot_download
from sklearn.pipeline import Pipeline

from skembeddings._hub import DEFAULT_README
from skembeddings.base import Serializable


class EmbeddingPipeline(Pipeline):
    def __init__(
        self,
        tokenizer: Serializable,
        model: Serializable,
        frozen: bool = False,
    ):
        self.tokenizer = tokenizer
        self.model = model
        self.frozen = frozen
        steps = [("tokenizer_model", tokenizer), ("embedding_model", model)]
        super().__init__(steps=steps)

    def freeze(self):
        self.frozen = True
        return self

    def unfreeze(self):
        self.frozen = False
        return self

    def fit(self, X, y=None, **kwargs):
        if self.frozen:
            return self
        super().fit(X, y=y, **kwargs)

    def partial_fit(self, X, y=None, classes=None, **kwargs):
        """
        Fits the components, but allow for batches.
        """
        if self.frozen:
            return self
        for name, step in self.steps:
            if not hasattr(step, "partial_fit"):
                raise ValueError(
                    f"Step {name} is a {step} which does"
                    "not have `.partial_fit` implemented."
                )
        for name, step in self.steps:
            if hasattr(step, "predict"):
                step.partial_fit(X, y, classes=classes, **kwargs)
            else:
                step.partial_fit(X, y)
            if hasattr(step, "transform"):
                X = step.transform(X)
        return self

    @property
    def config(self) -> Config:
        embedding: Serializable = self["embedding_model"]  # type: ignore
        tokenizer: Serializable = self["tokenizer_model"]  # type: ignore
        return tokenizer.config.merge(embedding.config)

    def to_disk(self, path: Union[str, Path]) -> None:
        embedding: Serializable = self["embedding_model"]  # type: ignore
        tokenizer: Serializable = self["tokenizer_model"]  # type: ignore
        path = Path(path)
        path.mkdir(exist_ok=True)
        config_path = path.joinpath("config.cfg")
        tokenizer_path = path.joinpath("tokenizer.bin")
        embedding_path = path.joinpath("embedding.bin")
        with open(embedding_path, "wb") as embedding_file:
            embedding_file.write(embedding.to_bytes())
        with open(tokenizer_path, "wb") as tokenizer_file:
            tokenizer_file.write(tokenizer.to_bytes())
        self.config.to_disk(config_path)

    @classmethod
    def from_disk(cls, path: Union[str, Path]) -> "EmbeddingPipeline":
        path = Path(path)
        config_path = path.joinpath("config.cfg")
        tokenizer_path = path.joinpath("tokenizer.bin")
        embedding_path = path.joinpath("embedding.bin")
        config = Config().from_disk(config_path)
        resolved = registry.resolve(config)
        with open(tokenizer_path, "rb") as tokenizer_file:
            tokenizer = resolved["tokenizer"].from_bytes(tokenizer_file.read())
        with open(embedding_path, "rb") as embedding_file:
            embedding = resolved["embedding"].from_bytes(embedding_file.read())
        return cls(tokenizer, embedding)

    def to_hub(self, repo_id: str, add_readme: bool = True) -> None:
        api = HfApi()
        api.create_repo(repo_id, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.to_disk(tmp_dir)
            if add_readme:
                with open(
                    Path(tmp_dir).joinpath("README.md"), "w"
                ) as readme_f:
                    readme_f.write(DEFAULT_README.format(repo=repo_id))
            api.upload_folder(
                folder_path=tmp_dir, repo_id=repo_id, repo_type="model"
            )

    @classmethod
    def from_hub(cls, repo_id: str) -> "EmbeddingPipeline":
        in_dir = snapshot_download(repo_id=repo_id)
        res = cls.from_disk(in_dir)
        return res.freeze()
