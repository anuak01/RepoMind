from tracker import storage  # circular: storage imports models


class Task:
    def __init__(self, title, done=False, tags=[]):
        self.title = title
        self.done = done
        self.tags = tags

    def mark_done(self):
        self.done = True
        storage.save(self)
