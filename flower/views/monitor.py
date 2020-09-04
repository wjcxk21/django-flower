from __future__ import absolute_import

from collections import defaultdict

from celery import states
from django.utils.decorators import method_decorator

from flower.utils import login_required_admin
from ..api.control import ControlHandler
from ..utils.broker import Broker
from ..views import BaseHandler


class BaseMonitor(BaseHandler):
    @staticmethod
    def _iteration(obj):
        """Do safe iteration"""
        try:
            for value in obj:
                yield value
        except RuntimeError:
            pass


class Monitor(BaseMonitor):

    @method_decorator(login_required_admin)
    def get(self, request):
        return self.render("flower/monitor.html")


class SucceededTaskMonitor(BaseMonitor):

    @method_decorator(login_required_admin)
    def get(self, request):
        timestamp = self.get_argument('lastquery', type=float)

        state = self.settings.state

        data = defaultdict(int)
        for task_key in self._iteration(state.tasks):
            task = state.tasks[task_key]
            if timestamp < task.timestamp and task.state == states.SUCCESS:
                data[task.worker.hostname] += 1
        for worker_key in state.workers.keys():
            if worker_key not in data:
                data[worker_key] = 0

        return self.write(data)


class TimeToCompletionMonitor(BaseMonitor):

    @method_decorator(login_required_admin)
    def get(self, request):
        timestamp = self.get_argument('lastquery', type=float)
        state = self.settings.state

        execute_time = 0
        queue_time = 0
        num_tasks = 0
        for task_key in self._iteration(state.tasks):
            task = state.tasks[task_key]
            if timestamp < task.timestamp and task.state == states.SUCCESS:
                # eta can make "time in queue" look really scary.
                if task.eta is not None:
                    continue

                if task.started is None or task.received is None or \
                        task.succeeded is None:
                    continue

                queue_time += task.started - task.received
                execute_time += task.succeeded - task.started
                num_tasks += 1

        avg_queue_time = (queue_time / num_tasks) if num_tasks > 0 else 0
        avg_execution_time = (execute_time / num_tasks) if num_tasks > 0 else 0

        result = {
            "Time in a queue": avg_queue_time,
            "Execution time": avg_execution_time,
        }
        return self.write(result)


class FailedTaskMonitor(BaseMonitor):

    @method_decorator(login_required_admin)
    def get(self, request):
        timestamp = self.get_argument('lastquery', type=float)
        state = self.settings.state

        data = defaultdict(int)
        for task_key in self._iteration(state.tasks):
            task = state.tasks[task_key]
            if timestamp < task.timestamp and task.state == states.FAILURE:
                data[task.worker.hostname] += 1
        for worker_key in state.workers.keys():
            if worker_key not in data:
                data[worker_key] = 0

        return self.write(data)


class BrokerMonitor(BaseMonitor):

    @method_decorator(login_required_admin)
    def get(self, request):
        app = self.settings.app
        try:
            broker = Broker(app.connection().as_uri(include_password=True),
                            http_api=self.settings.broker_api)
        except NotImplementedError:
            return self.write({})

        queue_names = ControlHandler.get_active_queue_names()
        queues = broker.queues(queue_names)

        data = defaultdict(int)
        for queue in queues:
            data[queue['name']] = queue.get('messages', 0)

        return self.write(data)
