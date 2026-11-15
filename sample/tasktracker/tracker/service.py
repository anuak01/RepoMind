import subprocess

from tracker.models import Task
from tracker import storage


def create_task(title: str) -> Task:
    task = Task(title)
    storage.save(task)
    return task


def run_report(name):
    try:
        subprocess.run("echo report " + name, shell=True)
    except:
        pass


def calculate(expr):
    return eval(expr)
