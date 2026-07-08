"""Auto-cycle controller for Showcase Mode: crossfades through every scene on
a timer. Started from the Launcher; ESC exits it back to the Launcher."""


class ShowcaseController:
    def __init__(self, app, scene_ids):
        self.app = app
        self.scene_ids = scene_ids
        self.active = False
        self._timer = 0.0
        self._index = 0

    def start(self):
        self.active = True
        self._index = 0
        self._timer = 0.0
        self.app.scene_manager.switch_to(self.scene_ids[self._index], transition="crossfade")
        self._announce()

    def stop(self):
        self.active = False

    def _announce(self):
        title = self.app.scene_manager.title_of(self.scene_ids[self._index])
        self.app.notifications.push(f"Now showing: {title}")

    def update(self, dt):
        if not self.active or self.app.scene_manager.transitioning:
            return
        self._timer += dt
        interval = max(30.0, self.app.settings.showcase_interval_min * 60.0)
        if self._timer >= interval:
            self._timer = 0.0
            self._index = (self._index + 1) % len(self.scene_ids)
            self.app.scene_manager.switch_to(self.scene_ids[self._index], transition="crossfade")
            self._announce()
