"""Minimal particle-list bookkeeping shared by any scene.

CityPulse's and LivingForest's particle systems are different enough in
behavior (simple data-sparks vs. multi-kind rain/snow/leaf/splash state
machines) that forcing them through one draw/update dispatch would just be an
awkward abstraction. What *is* identical between them is the alive/prune loop
every frame — that's the only part centralized here.
"""


class ParticlePool:
    def __init__(self):
        self.items = []

    def add(self, particle):
        self.items.append(particle)

    def update(self, dt, updater):
        """``updater(particle, dt) -> bool`` returns whether to keep it alive."""
        self.items = [p for p in self.items if updater(p, dt)]

    def draw(self, surf, drawer):
        for p in self.items:
            drawer(surf, p)

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)
