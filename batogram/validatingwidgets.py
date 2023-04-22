# Copyright (c) 2023 John Mears
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from abc import ABC, abstractmethod
from typing import Any, Tuple, List, Callable

import numpy as np
import tkinter as tk
import re


class AbstractValidatingWidgetMixin(ABC):
    """Base mixin class for any widget that we want to use in a validating frame."""
    # Can these colours be less hard coded?
    _NORMAL_BG = "#FFFFFF"
    _DIRTY_BG = "#FFFACA"
    _INVALID_BG = "#FFC0C0"

    def __init__(self, parent, controlling_frame, containing_frame, variable, value_validator):
        self._vem_parent = parent
        self._controlling_frame = controlling_frame
        self._containing_frame = containing_frame
        self._vem_value_validator = value_validator
        self._vem_is_dirty = False
        self._vem_is_valid = True
        self._vem_variable = variable
        # Note the initial value, so we know if it changed, and whether we can reset to it:
        self._vem_initial_value = None
        # Dependent widgets to enable/disable when our value changes:
        self._dependent_widgets: List[(AbstractValidatingWidgetMixin, Callable[[Any], bool])] = []

        # Ask for notification if the value changes, for example, because the user has edited it:
        if variable is not None:
            variable.trace_add("write", self.on_value_changed)

        # Register ourselves with the controlling frame:
        self._controlling_frame.register_validating_widget(self._containing_frame, self)

    def is_dirty(self):
        return self._vem_is_dirty

    def on_value_changed(self, var, index, mode):
        """Call this to signal that the user has edited the value. We use this to update the
        dirty state of the entry etc."""

        # Update the dirtiness:
        new_value = self.get_raw()
        is_dirty = False if new_value == self._vem_initial_value else True
        self._set_dirtiness(is_dirty)
        self.update_status()

        # Update any dependent widgets whose enabling depends on this one:
        for other_widget, adapter in self._dependent_widgets:
            enabled = adapter(new_value)
            # other_widget.set_enabled(enabled)
            state = tk.NORMAL if enabled else tk.DISABLED
            other_widget.configure(state=state)

    def on_reset(self):
        """Reset the entry to its initial value."""
        self._set_dirtiness(False)
        self._set_validity(True)
        self.update_status()
        self._controlling_frame.on_dirtiness_changed()

    def reset_to_initial(self):
        self._vem_variable.set(self._vem_initial_value)
        self._set_dirtiness(False)
        self._set_validity(True)
        self.update_status()
        self._controlling_frame.on_dirtiness_changed()

    def set_value(self, value):
        """Set the widget to a new value."""
        native = self.value_to_native(value)
        self._vem_variable.set(native)
        self._vem_initial_value = native
        self._set_dirtiness(False)
        self._set_validity(True)
        self.update_status()
        self._controlling_frame.on_dirtiness_changed()

    def validate_value(self):
        """Validate and evaluate the field value. If it is OK,
        return the value, reset the field to the value; otherwise, return None and
        an error message."""

        result_msg = None       # By default, it's valid.
        value = None
        try:
            # Parse and validate the value:
            s = self._vem_variable.get()
            try:
                value = self.native_to_value(s)  # Might raise a ValueError
            except ValueError as e:
                # Paranoid, shouldn't happen:
                result_msg = "Unable to parse field value {}".format(s)

            if self._vem_value_validator:
                error_msg = self._vem_value_validator(value)
                if error_msg:
                    result_msg = error_msg
        finally:
            # As a side effect, highlight and focus the entruy:
            self._set_validity(result_msg is None)
            self.update_status()
            self.focus_set()
            return result_msg

    def get_value(self):
        native = self._vem_variable.get()
        value = self.native_to_value(native)     # Might raise a ValueError
        return value

    def apply_entry(self):
        """Call this only if evaluate_entry succeeds, set the field to is current value."""
        value = self.native_to_value(self._vem_variable.get())
        self._vem_initial_value = value
        self._set_dirtiness(False)
        self._set_validity(True)
        self.update_status()
        self._controlling_frame.on_dirtiness_changed()

    @abstractmethod
    def update_status(self):
        raise NotImplementedError

    def register_dependent_widgets(self, adapter: Callable[[Any], bool], other_widgets: List['__class__']):
        """Register another widget to be enabled or disable according to the
        state of this one."""

        for other in other_widgets:
            self._dependent_widgets.append((other, adapter))

    def _set_dirtiness(self, is_dirty):
        was_dirty = self._vem_is_dirty
        self._vem_is_dirty = is_dirty
        # Notify the controller if dirtiness changed:
        if was_dirty != self._vem_is_dirty:
            self._controlling_frame.on_dirtiness_changed()

    def _set_validity(self, is_valid):
        self._vem_is_valid = is_valid
        self.update_status()

    def native_to_value(self, native):
        raise NotImplementedError()

    # def set_enabled(self, enabled: bool):
    #     state = tk.NORMAL if enabled else tk.DISABLED
    #     self.configure(state=state)

    @abstractmethod
    def value_to_native(self, value):
        raise NotImplementedError()

    @abstractmethod
    def get_raw(self):
        raise NotImplementedError


class AbstractValidatingEntryMixin(AbstractValidatingWidgetMixin, ABC):
    """Base mixin class for Entry widgets that we want to use in a validating frame."""
    def __init__(self, parent, controlling_frame, containing_frame, variable, value_validator):
        AbstractValidatingWidgetMixin.__init__(self, parent, controlling_frame, containing_frame,
                                               variable, value_validator=value_validator)
        self._vem_default_bg = self._NORMAL_BG

    def on_reset(self):
        super().on_reset()
        self.set(self._vem_initial_value)

    def get_raw(self):
        return self.get()

    def update_status(self):
        if not self._vem_is_valid:
            self.configure(bg=self._INVALID_BG)
        elif self._vem_is_dirty:
            self.configure(bg=self._DIRTY_BG)
        else:
            self.configure(bg=self._NORMAL_BG)


class AbstractValidatingEntry(tk.Entry, AbstractValidatingEntryMixin, ABC):
    """Ready mixed Entry widget base calss that we want to use in a validating frame."""

    def __init__(self, parent, controlling_frame, container, width, validate, validatecommand, value_validator):
        self._textvariable = tk.StringVar()    # Use a string regardless of data type
        tk.Entry.__init__(self, parent, width=width, validate=validate, validatecommand=validatecommand,
                          textvariable=self._textvariable)
        AbstractValidatingEntryMixin.__init__(self, parent, controlling_frame, container, variable=self._textvariable,
                                              value_validator=value_validator)


class DoubleValidatingEntry(AbstractValidatingEntry):
    """Oven ready validating entry for double data"""
    def __init__(self, parent, controlling_frame, container, width, decimal_places, scaler=1.0, value_validator=None):
        AbstractValidatingEntry.__init__(self, parent, controlling_frame, container, width, validate='key',
                                         validatecommand=(parent.validatecommand_float, '%V', '%P'), value_validator=value_validator)
        self._decimal_places = decimal_places
        self._scaler = scaler

    def value_to_native(self, value):
        return np.format_float_positional(value / self._scaler, precision=self._decimal_places, fractional=True, trim='-')

    def native_to_value(self, native):
        """This can throw ValueError, though won't if the field validation regex is right"""
        return float(native) * self._scaler


class ValidatingCheckbutton(tk.Checkbutton, AbstractValidatingWidgetMixin):
    """Oven ready validating entry for check boxes"""

    def __init__(self, parent, controlling_frame, container, text, value_validator=None):
        variable = tk.IntVar()
        tk.Checkbutton.__init__(self, parent, text=text, variable=variable)
        AbstractValidatingWidgetMixin.__init__(self, parent, controlling_frame, container, variable, value_validator)
        self._vc_bg_colour = self["bg"]

    def native_to_value(self, native):
        return False if self._vem_variable.get() == 0 else True

    def value_to_native(self, value):
        return 1 if value else 0

    def get_raw(self):
        return self._vem_variable.get()

    def update_status(self):
        if not self._vem_is_valid:
            self.configure(bg=self._INVALID_BG)
        elif self._vem_is_dirty:
            self.configure(bg=self._DIRTY_BG)
        else:
            self.configure(bg=self._vc_bg_colour)


class ValidatingRadiobutton(tk.Radiobutton, AbstractValidatingWidgetMixin):
    """Oven ready validating entry for check boxes"""

    def __init__(self, parent, controlling_frame, container, text, variable, value, value_validator=None):
        tk.Radiobutton.__init__(self, parent, text=text, variable=variable, value=value)
        AbstractValidatingWidgetMixin.__init__(self, parent, controlling_frame, container, variable, value_validator)
        self._vc_bg_colour = self["bg"]

    def native_to_value(self, native):
        return self._vem_variable.get()

    def value_to_native(self, value):
        return value

    def get_raw(self):
        return self._vem_variable.get()

    def update_status(self):
        if not self._vem_is_valid:
            self.configure(bg=self._INVALID_BG)
        elif self._vem_is_dirty:
            self.configure(bg=self._DIRTY_BG)
        else:
            self.configure(bg=self._vc_bg_colour)


class ValidatingOptionMenu(tk.OptionMenu, AbstractValidatingWidgetMixin, ABC):
    """Oven ready validating entry for options menus"""

    def __init__(self, parent, controlling_frame, container, values, value_validator=None):
        variable = tk.StringVar()
        super().__init__(parent, variable, *values)
        AbstractValidatingWidgetMixin.__init__(self, parent, controlling_frame, container, variable, value_validator)
        self._vc_bg_colour = self["bg"]

    @abstractmethod
    def native_to_value(self, native):
        raise NotImplementedError()

    @abstractmethod
    def value_to_native(self, value):
        raise NotImplementedError()

    def get_raw(self):
        return self._vem_variable.get()

    def update_status(self):
        if not self._vem_is_valid:
            self.configure(bg=self._INVALID_BG)
        elif self._vem_is_dirty:
            self.configure(bg=self._DIRTY_BG)
        else:
            self.configure(bg=self._vc_bg_colour)


class ValidatingIntOptionMenu(ValidatingOptionMenu):
    """Oven ready validating entry for options menus"""

    def __init__(self, parent, controlling_frame, values, value_validator=None):
        super().__init__(parent, controlling_frame, values, value_validator)

    def native_to_value(self, native):
        return int(native)

    def value_to_native(self, value):
        return str(value)


class ValidatingFloatOptionMenu(ValidatingOptionMenu):
    """Oven ready validating entry for options menus"""

    def __init__(self, parent, controlling_frame, container, values, value_validator=None):
        super().__init__(parent, controlling_frame, container, values, value_validator)

    def native_to_value(self, native):
        return float(native)

    def value_to_native(self, value):
        return str(value)


class ValidatingMapOptionMenu(ValidatingOptionMenu):
    def __init__(self, parent: tk.Widget, controlling_frame: tk.Widget, container: tk.Widget,
                 dictionary: dict[Any, str], value_validator=None):
        self._dictionary = dictionary
        keys: list[Any] = [k for k in dictionary.keys()]
        keys.sort()
        values = [dictionary[k] for k in keys]
        super().__init__(parent, controlling_frame, container, tuple(values), value_validator)

    def native_to_value(self, native):
        # Only good for short lists:
        for k, v in self._dictionary.items():
            if v == native:
                return k

        raise ValueError()

    def value_to_native(self, value):
        return self._dictionary[value]


class ValidatingFrameHelper:
    """A handy helper for any frame containing validating widgets"""
    _RE_FLOAT = re.compile(r'[+-]?[0-9]*\.?[0-9]*')

    def __init__(self, parent, settings):
        self._vfm_parent = parent
        self._vfm_settings = settings
        self.validatecommand_float = self.register(self.float_or_empty_entry_validator)

    def float_or_empty_entry_validator(self, action, p):
        result = self._RE_FLOAT.fullmatch(p)
        return True if result is not None else False

    @staticmethod
    def double_value_validator(v: float, minimum_value=None, maximum_value=None, minimum_entry=None, message=None):
        if minimum_value is not None:
            if v < minimum_value:
                return message if message is not None else "Value must be greater than {}".format(minimum_value)

        if maximum_value is not None:
            if v > maximum_value:
                return message if message is not None else "Value must be less than {}".format(maximum_value)

        if minimum_entry is not None:
            # Compare with the value of another field:
            v_other = minimum_entry.get_value()
            if v < v_other:
                return message if message is not None else "Value must be at least {}".format(v_other)

        return None


class ControllingFrameMixin:
    """A mixin for controlling frames that contain the apply/reset buttons and interface with the rest
    of the application."""
    def __init__(self):
        self._cfm_widgets: List[Tuple[tk.Frame, tk.Widget]] = []
        self._recalculate()

    def register_validating_widget(self, containing_frame, widget):
        self._cfm_widgets.append((containing_frame, widget))

    def on_dirtiness_changed(self):
        is_dirty = self._recalculate()
        enabled = tk.NORMAL if is_dirty else tk.DISABLED
        self.enable_controlling_buttons(enabled)
        self._apply_button["state"] = enabled
        self._cancel_button["state"] = enabled

    def _recalculate(self):
        is_dirty = False
        for _, w in self._cfm_widgets:
            if w.is_dirty():
                is_dirty = True
        return is_dirty

    def do_cancel(self):
        """Reset all widgets to their initial values."""
        for _, w in self._cfm_widgets:
            w.reset_to_initial()

    def do_validate(self):
        # Validate all fields individually, then at frame level.
        # If there is a failure, set the failure error text, and bail out.
        # Otherwise:
        #   Confirm all current values as reset (None as parameter to set_value?)
        #   Extract all data values, invoke a callback with the updated settings.

        # Validate each field:
        for c, w in self._cfm_widgets:
            message = w.validate_value()
            if message:
                # Highlight the erroneous entry and give it the focus:

                # Show the error to the user, and bail out:
                self.show_error(c, message)
                return False

        return True

    def do_apply(self):
        for _, w in self._cfm_widgets:
            w.apply_entry()
