import random
from typing import List

import torch
from coati.experience_maker.base import Experience

from colossalai.logging import get_dist_logger

from .base import ExperienceBuffer
from .utils import BufferItem, make_experience_batch, split_experience_batch

logger = get_dist_logger()


class NaiveExperienceBuffer(ExperienceBuffer):
    """Naive experience buffer class. It stores experience.

    Args:
        sample_batch_size (int): Batch size when sampling.
        limit (int, optional): Limit of number of experience samples. A number <= 0 means unlimited. Defaults to 0.
        cpu_offload (bool, optional): Whether to offload experience to cpu when sampling. Defaults to True.
    """

    def __init__(self, sample_batch_size: int, limit: int = 0, cpu_offload: bool = True) -> None:
        super().__init__(sample_batch_size, limit)
        self.cpu_offload = cpu_offload
        self.target_device = torch.device(f"cuda:{torch.cuda.current_device()}")
        # TODO(ver217): add prefetch
        self.items: List[BufferItem] = []
        self.rng_sequence = []
        self.ptr = 0

    @torch.no_grad()
    def append(self, experience: Experience) -> None:
        if self.cpu_offload:
            experience.to_device(torch.device("cpu"))
        items = split_experience_batch(experience)
        self.items.extend(items)

        if self.limit > 0:
            samples_to_remove = len(self.items) - self.limit
            if samples_to_remove > 0:
                logger.warning(f"Experience buffer is full. Removing {samples_to_remove} samples.")
                self.items = self.items[samples_to_remove:]
        self.rng_sequence = [i for i in range(len(self.items))]
        random.shuffle(self.rng_sequence)
        self.ptr = 0

    def clear(self) -> None:
        self.items.clear()

    @torch.no_grad()
    def sample(self) -> Experience:
        """
        Randomly samples experiences from the buffer.

        Returns:
            A batch of sampled experiences.
        """
        items = []
        for _ in range(self.sample_batch_size):
            self.ptr = (self.ptr + 1) % len(self.items)
            items.append(self.items[self.rng_sequence[self.ptr]])
        experience = make_experience_batch(items)
        if self.cpu_offload:
            experience.to_device(self.target_device)
        return experience

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> BufferItem:
        return self.items[idx]

    def collate_fn(self, batch) -> Experience:
        experience = make_experience_batch(batch)
        return experience
