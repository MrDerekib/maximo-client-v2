"""Cooperative priorities for MD jobs; extension automations remain independent."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
import itertools
import logging
import threading

HIGH, MANUAL, AUTOMATIC = 0, 1, 2


class JobCancelled(RuntimeError):
    pass


class ReadYield(RuntimeError):
    """A read-only global download can be abandoned and obtained fresh after yielding."""


class JobCounter:
    """Tracks queued/running work for UI/shutdown; serialization belongs to the coordinator."""
    def __init__(self):
        self.count = 0
        self.guard = threading.Lock()

    def acquire(self, blocking=True):
        with self.guard:
            self.count += 1
        return True

    def release(self):
        with self.guard:
            if self.count <= 0:
                raise RuntimeError('Unbalanced job counter')
            self.count -= 1

    def locked(self):
        with self.guard:
            return self.count > 0


@dataclass(eq=False)
class Ticket:
    label: str
    priority: int
    sequence: int
    callback: object = None
    cancel: object = None
    phase: str = ''
    ot: str = ''
    completed: int = 0
    total: int = 0
    read_interruptible: bool = False
    id: str = field(default='')


class Coordinator:
    def __init__(self):
        self.condition = threading.Condition()
        self.sequence = itertools.count()
        self.active = None
        self.queue = []
        self.local = threading.local()
        self.listeners = []
        self.stopping = False

    def subscribe(self, listener):
        with self.condition:
            self.listeners.append(listener)
        def unsubscribe(*_):
            with self.condition:
                if listener in self.listeners:
                    self.listeners.remove(listener)
        return unsubscribe

    def _emit(self, kind, ticket, message):
        event = {'kind':kind,'id':ticket.id,'label':ticket.label,'priority':ticket.priority,
                 'ot':ticket.ot,'completed':ticket.completed,'total':ticket.total,
                 'embedded':ticket.callback is not None,'message':message}
        logging.info('Prioridades MD: %s · %s',kind,message)
        if ticket.callback is not None and kind in ('waiting','started','resumed'):
            try:
                ticket.callback(message)
            except Exception:
                logging.exception('No se pudo notificar la espera de tarea')
        for listener in tuple(self.listeners):
            try:
                listener(event)
            except Exception:
                logging.exception('No se pudo comunicar la prioridad de tarea')

    def _waiting_text(self, ticket):
        if self.active is None:
            return f'Esperando turno para «{ticket.label}».'
        active = self.active
        current = active.phase or active.label
        if active.ot:
            current += f' · OT {active.ot}'
        suffix = 'Se pausará su cola' if active.priority > ticket.priority else 'Terminará su operación'
        return f'Esperando turno. Terminando {current}. {suffix} y comenzará «{ticket.label}».'

    def _acquire(self, ticket, resumed=False):
        self.queue.append(ticket)
        announced = False
        while True:
            if self.stopping or (ticket.cancel is not None and ticket.cancel.is_set()):
                self.queue.remove(ticket)
                self._emit('cancelled',ticket,f'Cancelada {ticket.label} antes de comenzar.')
                self.condition.notify_all()
                raise JobCancelled('Tarea cancelada por cierre de MD.' if self.stopping else
                                   'Tarea cancelada por el usuario antes de comenzar.')
            first = min(self.queue,key=lambda t:(t.priority,t.sequence))
            if self.active is None and first is ticket:
                self.queue.remove(ticket)
                self.active = ticket
                self._emit('resumed' if resumed else 'started',ticket,
                           f'{"Reanudando" if resumed else "Iniciando"} {ticket.label}' +
                           (f' · {ticket.completed}/{ticket.total} OT revisadas.' if ticket.total else '.'))
                return
            if not announced:
                self._emit('waiting',ticket,self._waiting_text(ticket))
                announced = True
            self.condition.wait(.25)

    @contextmanager
    def job(self, label, priority, callback=None, cancel=None):
        existing = getattr(self.local,'ticket',None)
        if existing is not None:
            yield existing
            return
        sequence = next(self.sequence)
        ticket = Ticket(label,priority,sequence,callback,cancel,id=f'job-{sequence}')
        with self.condition:
            self._acquire(ticket)
        self.local.ticket = ticket
        try:
            yield ticket
        finally:
            with self.condition:
                if self.active is ticket:
                    self.active = None
                self.local.ticket = None
                self._emit('finished',ticket,f'Finalizada {ticket.label}.')
                self.condition.notify_all()

    def checkpoint(self, phase, ot='', completed=0, total=0, on_pause=None):
        ticket = getattr(self.local,'ticket',None)
        if ticket is None:
            return False
        paused = False
        with self.condition:
            if self.stopping:
                raise JobCancelled('Tarea cancelada por cierre de MD.')
            ticket.completed,ticket.total = completed,total
            if any(t.priority < ticket.priority for t in self.queue):
                # This callback may only retire the current job's browser, after a
                # complete OT or before a global import, never during a confirmation.
                if on_pause is not None:
                    on_pause()
                self._emit('paused',ticket,f'{ticket.label} pausada · {completed}/{total} OT revisadas.')
                self.active = None
                ticket.sequence = next(self.sequence)
                self.condition.notify_all()
                self._acquire(ticket,resumed=True)
                paused = True
            ticket.phase,ticket.ot,ticket.completed,ticket.total = phase,str(ot),completed,total
        return paused

    def should_yield_read(self):
        ticket = getattr(self.local,'ticket',None)
        with self.condition:
            return bool(ticket and ticket.read_interruptible and
                        (self.stopping or any(t.priority < ticket.priority for t in self.queue)))

    @contextmanager
    def interruptible_read(self):
        ticket = getattr(self.local,'ticket',None)
        if ticket is not None:
            ticket.read_interruptible = True
        try:
            yield
        finally:
            if ticket is not None:
                ticket.read_interruptible = False

    def shutdown(self):
        with self.condition:
            self.stopping = True
            self.condition.notify_all()


coordinator = Coordinator()


def scheduled(label, default_priority):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            priority = kwargs.pop('job_priority',default_priority)
            callback = kwargs.pop('job_waiting',None)
            cancel = kwargs.pop('job_cancel_event',None)
            name = kwargs.pop('job_label',label)
            with coordinator.job(name,priority,callback,cancel):
                return function(*args,**kwargs)
        return run
    return decorate
