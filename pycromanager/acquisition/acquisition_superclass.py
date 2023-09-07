"""
Generic acquisition functionality used by both Python and Java backends
"""

import copy
import types
import numpy as np
from typing import Union, List, Iterable
import warnings
from abc import ABCMeta, abstractmethod
from docstring_inheritance import NumpyDocstringInheritanceMeta
import queue
import weakref
from pycromanager.acq_future import AcqNotification, AcquisitionFuture
import os
import threading
from inspect import signature


class AcqAlreadyCompleteException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

# Subclasses inherit docstrings from abstract base class
class Meta(ABCMeta, NumpyDocstringInheritanceMeta):
  pass

class Acquisition(metaclass=Meta):

    def __init__(
            self,
            directory: str = None,
            name: str = "default_acquisition_name",
            image_process_fn: callable = None,
            event_generation_hook_fn: callable = None,
            pre_hardware_hook_fn: callable = None,
            post_hardware_hook_fn: callable = None,
            post_camera_hook_fn: callable = None,
            notification_callback_fn: callable = None,
            image_saved_fn: callable = None,
            napari_viewer=None,
            debug: int = False
    ):
        """
        Parameters
        ----------
        directory : str
            saving directory for this acquisition. If it is not supplied, the image data will be stored in RAM
        name : str
            Name of the acquisition. This will be used to generate the folder where the data is saved.
        image_process_fn : Callable
            image processing function that will be called on each image that gets acquired.
            Can either take two arguments (image, metadata) where image is a numpy array and metadata is a dict
            containing the corresponding image metadata. Or a three argument version is accepted, which accepts (image,
            metadata, queue), where queue is a Queue object that holds upcoming acquisition events. The function
            should return either an (image, metadata) tuple or a list of such tuples
        event_generation_hook_fn : Callable
            hook function that will as soon as acquisition events are generated (before hardware sequencing optimization
            in the acquisition engine. This is useful if one wants to modify acquisition events that they didn't generate
            (e.g. those generated by a GUI application). Accepts either one argument (the current acquisition event)
            or two arguments (current event, event_queue)
        pre_hardware_hook_fn : Callable
            hook function that will be run just before the hardware is updated before acquiring
            a new image. In the case of hardware sequencing, it will be run just before a sequence of instructions are
            dispatched to the hardware. Accepts either one argument (the current acquisition event) or two arguments
            (current event, event_queue)
        post_hardware_hook_fn : Callable
            hook function that will be run just before the hardware is updated before acquiring
            a new image. In the case of hardware sequencing, it will be run just after a sequence of instructions are
            dispatched to the hardware, but before the camera sequence has been started. Accepts either one argument
            (the current acquisition event) or two arguments (current event, event_queue)
        post_camera_hook_fn : Callable
            hook function that will be run just after the camera has been triggered to snapImage or
            startSequence. A common use case for this hook is when one want to send TTL triggers to the camera from an
            external timing device that synchronizes with other hardware. Accepts either one argument (the current
            acquisition event) or two arguments (current event, event_queue)
        notification_callback_fn : Callable
            (Experimental) function that will be called whenever a notification is received from the acquisition engine. These
            include various stages of the control of hardware and the camera and saving of images. Notification
            callbacks will execute asynchronously with respect to the acquisition process. The supplied function
            should take a single argument, which will be an AcqNotification object. It should execute quickly,
             so as to not back up the processing of other notifications.
        image_saved_fn : Callable
            function that takes two arguments (the Axes of the image that just finished saving, and the Dataset)
            or three arguments (Axes, Dataset and the event_queue) and gets called whenever a new image is written to
            disk
        napari_viewer : napari.Viewer
            Provide a napari viewer to display acquired data in napari (https://napari.org/) rather than the built-in
            NDViewer. None by default. Data is added to the 'pycromanager acquisition' layer, which may be pre-configured by
            the user
        debug : bool
            whether to print debug messages
        """
        self._debug = debug
        self._dataset = None
        self._finished = False
        self._exception = None
        self._napari_viewer = None
        self._notification_queue = queue.Queue(100)
        self._image_notification_queue = queue.Queue(100)
        self._acq_futures = []
        self._image_process_fn = image_process_fn

        pass


    def _start_notification_dispatcher(self, notification_callback_fn):
        """
        Thread that runs a function that pulls notifications from the queueand dispatches
        them to the appropriate listener
        """
        def dispatch_notifications():
            events_finished = False
            data_sink_finished = False
            while True:
                # dispatch notifications to all listeners
                notification = self._notification_queue.get()

                if AcqNotification.is_acquisition_finished_notification(notification):
                    events_finished = True
                elif AcqNotification.is_data_sink_finished_notification(notification):
                    data_sink_finished = True
                # notify acquisition futures so they can stop blocking
                for future in self._acq_futures:
                    strong_ref = future()
                    if strong_ref is not None:
                        strong_ref._notify(notification)
                # alert user-specified notification callback
                if notification_callback_fn is not None:
                    notification_callback_fn(notification)

                if events_finished and data_sink_finished:
                    break

        dispatcher_thread = threading.Thread(
            target=dispatch_notifications,
            name="NotificationDispatcherThread",
        )
        dispatcher_thread.start()
        return dispatcher_thread

    @abstractmethod
    def get_dataset(self):
        """
        Get access to the dataset backing this acquisition
        """

    @abstractmethod
    def await_completion(self):
        """
        Wait for acquisition to finish and resources to be cleaned up. If data is being written to
        disk, this will wait for the data to be written before returning.
        """

    @abstractmethod
    def get_viewer(self):
        """
        Return a reference to the current viewer, if the show_display argument
        was set to True. The returned object is either an instance of NDViewer or napari.Viewer()
        """

    def mark_finished(self):
        """
        Signal to acquisition that no more events will be added and it is time to initiate shutdown.
        This is only needed if the context manager (i.e. "with Acquisition...") is not used.
        """
        # Some acquisition types (e.g. ExploreAcquisitions) generate their own events
        # and don't send events over a port
        if self._event_queue is not None:
            # this should shut down storage and viewer as appropriate
            self._event_queue.put(None)

    def acquire(self, event_or_events: dict or list):
        """
        Submit an event or a list of events for acquisition. A single event is a python dictionary
        with a specific structure. The acquisition engine will determine if multiple events can
        be merged into a hardware sequence and executed at once without computer-hardware communication in
        between. This sequencing will only take place for events that are within a single call to acquire,
        so if you want to ensure this doesn't happen, call acquire multiple times with each event in a
        list individually.

        Parameters
        ----------
        event_or_events  : list, dict
            A single acquistion event (a dict) or a list of acquisition events

        """
        if self._acq.are_events_finished():
            raise AcqAlreadyCompleteException(
                'Cannot submit more events because this acquisition is already finished')

        if event_or_events is None:
            # manual shutdown
            self._event_queue.put(None)
            return

        _validate_acq_events(event_or_events)

        axes_or_axes_list = event_or_events['axes'] if type(event_or_events) == dict\
            else [e['axes'] for e in event_or_events]
        acq_future = AcquisitionFuture(self, axes_or_axes_list)
        self._acq_futures.append(weakref.ref(acq_future))
        # clear out old weakrefs
        self._acq_futures = [f for f in self._acq_futures if f() is not None]

        self._event_queue.put(event_or_events)
        return acq_future



    def abort(self, exception=None):
        """
        Cancel any pending events and shut down immediately

        Parameters
        ----------
        exception  : Exception
            The exception that is the reason abort is being called
        """
        # Store the exception that caused this
        if exception is not None:
            self._exception = exception

        # Clear any pending events on the python side, if applicable
        if self._event_queue is not None:
            self._event_queue.queue.clear()
            # Don't send any more events. The event sending thread should know shut itself down by
            # checking the status of the acquisition
        self._acq.abort()

    def _create_event_queue(self):
        """Create thread safe queue for events so they can be passed from multiple processes"""
        self._event_queue = queue.Queue()

    def _call_image_process_fn(self, image, metadata):
        params = signature(self._process_fn).parameters
        processed = None
        if len(params) == 2 or len(params) == 3:
            try:
                if len(params) == 2:
                    processed = self._process_fn(image, metadata)
                elif len(params) == 3:
                    processed = self._process_fn(image, metadata, self._event_queue)
            except Exception as e:
                self.abort(Exception("exception in image processor: {}".format(e)))

        else:
            self.abort(Exception(
                "Incorrect number of arguments for image processing function, must be 2 or 3"
            ))
        return processed

    ########  Context manager (i.e. "with Acquisition...") ###########
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.mark_finished()
        # now wait on it to finish
        self.await_completion()


def _validate_acq_events(events: dict or list):
    """
    Validate if supplied events are a dictionary or a list of dictionaries
    that contain valid events. Throw an exception if not

    Parameters
    ----------
    events : dict or list

    """
    if isinstance(events, dict):
        _validate_acq_dict(events)
    elif isinstance(events, list):
        if len(events) == 0:
            raise Exception('events list cannot be empty')
        for event in events:
            if isinstance(event, dict):
                _validate_acq_dict(event)
            else:
                raise Exception('events must be a dictionary or a list of dictionaries')
    else:
        raise Exception('events must be a dictionary or a list of dictionaries')

def _validate_acq_dict(event: dict):
    """
    Validate event dictionary, and raise an exception or supply a warning and fix it if something is incorrect

    Parameters
    ----------
    event : dict

    """
    if 'axes' not in event.keys():
        raise Exception('event dictionary must contain an \'axes\' key. This event will be ignored')
    if 'row' in event.keys():
        warnings.warn('adding \'row\' as a top level key in the event dictionary is deprecated and will be disallowed in '
                      'a future version. Instead, add \'row\' as a key in the \'axes\' dictionary')
        event['axes']['row'] = event['row']
    if 'col' in event.keys():
        warnings.warn('adding \'col\' as a top level key in the event dictionary is deprecated and will be disallowed in '
                      'a future version. Instead, add \'column\' as a key in the \'axes\' dictionary')
        event['axes']['column'] = event['col']

    # TODO check for the validity of other acquisition event fields, and make sure that there aren't unexpected
    #   other fields, to help users catch simple errors


def multi_d_acquisition_events(
    num_time_points: int=None,
    time_interval_s: Union[float, List[float]]=0,
    z_start: float=None,
    z_end: float=None,
    z_step: float=None,
    channel_group: str=None,
    channels: list=None,
    channel_exposures_ms: list=None,
    xy_positions: Iterable=None,
    xyz_positions: Iterable=None,
    position_labels: List[str]=None,
    order: str="tpcz",
):
    """Convenience function for generating the events of a typical multi-dimensional acquisition (i.e. an
    acquisition with some combination of multiple timepoints, channels, z-slices, or xy positions)

    Parameters
    ----------
    num_time_points : int
        How many time points if it is a timelapse (Default value = None)
    time_interval_s : float or list of floats
        the minimum interval between consecutive time points in seconds. If set to 0, the 
        acquisition will go as fast as possible. If a list is provided, its length should 
        be equal to 'num_time_points'. Elements in the list are assumed to be the intervals
        between consecutive timepoints in the timelapse. First element in the list indicates
        delay before capturing the first image (Default value = 0)
    z_start : float
        z-stack starting position, in µm. If xyz_positions is given z_start is relative
        to the points' z position. (Default value = None)
    z_end : float
        z-stack ending position, in µm. If xyz_positions is given z_start is
        relative to the points' z position. (Default value = None)
    z_step : float
        step size of z-stack, in µm (Default value = None)
    channel_group : str
        name of the channel group (which should correspond to a config group in micro-manager) (Default value = None)
    channels : list of strings
        list of channel names, which correspond to possible settings of the config group
        (e.g. ['DAPI', 'FITC']) (Default value = None)
    channel_exposures_ms : list of floats or ints
        list of camera exposure times corresponding to each channel. The length of this list
        should be the same as the the length of the list of channels (Default value = None)
    xy_positions : iterable
        An array of shape (N, 2) containing N (X, Y) stage coordinates. (Default value = None)
    xyz_positions : iterable
        An array of shape (N, 3) containing N (X, Y, Z) stage coordinates. (Default value = None).
        If passed then z_start, z_end, and z_step will be relative to the z_position in xyz_positions. (Default value = None)
    position_labels : iterable
        An array of length N containing position labels for each of the XY stage positions. (Default value = None)
    order : str
        string that specifies the order of different dimensions. Must have some ordering of the letters
        c, t, p, and z. For example, 'tcz' would run a timelapse where z stacks would be acquired at each channel in
        series. 'pt' would move to different xy stage positions and run a complete timelapse at each one before moving
        to the next (Default value = 'tpcz')

    Returns
    -------
    events : dict
    """
    if xy_positions is not None and xyz_positions is not None:
        raise ValueError(
            "xyz_positions and xy_positions are incompatible arguments that cannot be passed together"
        )
    order = order.lower()
    if "p" in order and "z" in order and order.index("p") > order.index("z"):
        raise ValueError(
            "This function requires that the xy position come earlier in the order than z"
        )
    if isinstance(time_interval_s, list):
        if len(time_interval_s) != num_time_points:
            raise ValueError(
                "Length of time interval list should be equal to num_time_points"
            )
    if position_labels is not None:
        if xy_positions is not None and len(xy_positions) != len(position_labels):
            raise ValueError("xy_positions and position_labels must be of equal length")
        if xyz_positions is not None and len(xyz_positions) != len(position_labels):
            raise ValueError("xyz_positions and position_labels must be of equal length")
    
    # If any of z_start, z_step, z_end are provided, then they should all be provided
    # Here we can't use `all` as some of the values of z_start, z_step, z_end
    # may be zero and all((0,)) = False
    has_zsteps = False
    if any([z_start, z_step, z_end]):
        if not None in [z_start, z_step, z_end]:
            has_zsteps = True
        else:
            raise ValueError('All of z_start, z_step, and z_end must be provided')

    z_positions = None
    if xy_positions is not None:
        xy_positions = np.asarray(xy_positions)
        z_positions = None
    elif xyz_positions is not None:
        xyz_positions = np.asarray(xyz_positions)
        xy_positions = xyz_positions[:, :2]
        z_positions = xyz_positions[:, 2][:, None]

    if has_zsteps:
        z_rel = np.arange(z_start, z_end + z_step, z_step)
        if z_positions is None:
            z_positions = z_rel
            if xy_positions is not None:
                z_positions = np.broadcast_to(
                    z_positions, (xy_positions.shape[0], z_positions.shape[0])
                )
        else:
            pos = []
            for z in z_positions:
                pos.append(z + z_rel)
            z_positions = np.asarray(pos)

    if position_labels is None and xy_positions is not None:
        position_labels = list(range(len(xy_positions)))

    def generate_events(event, order):
        if len(order) == 0:
            yield event
            return
        elif order[0] == "t" and num_time_points is not None and num_time_points > 0:
            time_indices = np.arange(num_time_points)
            if isinstance(time_interval_s, list):
                absolute_start_times = np.cumsum(time_interval_s)
            for time_index in time_indices:
                new_event = copy.deepcopy(event)
                new_event["axes"]["time"] = time_index
                if isinstance(time_interval_s, list):
                    new_event["min_start_time"] = absolute_start_times[time_index]
                else:
                    if time_interval_s != 0:
                        new_event["min_start_time"] = time_index * time_interval_s
                yield generate_events(new_event, order[1:])
        elif order[0] == "z" and z_positions is not None:
            if "axes" in event and "position" in event["axes"]:
                pos_idx = position_labels.index(event["axes"]["position"])
                zs = z_positions[pos_idx]
            else:
                zs = z_positions

            for z_index, z in enumerate(zs):
                new_event = copy.deepcopy(event)
                new_event["axes"]["z"] = z_index
                new_event["z"] = z
                yield generate_events(new_event, order[1:])
        elif order[0] == "p" and xy_positions is not None:
            for p_label, xy in zip(position_labels, xy_positions):
                new_event = copy.deepcopy(event)
                new_event["axes"]["position"] = p_label
                new_event["x"] = xy[0]
                new_event["y"] = xy[1]
                yield generate_events(new_event, order[1:])
        elif order[0] == "c" and channel_group is not None and channels is not None:
            for i in range(len(channels)):
                new_event = copy.deepcopy(event)
                new_event["config_group"] = [channel_group,  channels[i]]
                new_event["axes"]["channel"] = channels[i]
                if channel_exposures_ms is not None:
                    new_event["exposure"] = channel_exposures_ms[i]
                yield generate_events(new_event, order[1:])
        else:
            # this axis appears to be missing
            yield generate_events(event, order[1:])

    # collect all events into a single list
    base_event = {"axes": {}}
    events = []

    def appender(next):
        """

        Parameters
        ----------
        next :


        Returns
        -------

        """
        if isinstance(next, types.GeneratorType):
            for n in next:
                appender(n)
        else:
            events.append(next)

    appender(generate_events(base_event, order))
    return events


