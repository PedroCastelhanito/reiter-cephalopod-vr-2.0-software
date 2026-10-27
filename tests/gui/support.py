"""Shared GUI test helpers that are not fixtures."""


class ParameterDocument:
    """Document sink for parameter-widget tests, independent of planner navigation."""

    def __init__(self, window):
        from cephvr.gui.protocol_document import blank_program
        from cephvr.gui.stimulus_parameters import StimulusParameters

        self.parameters = StimulusParameters()
        self.parameters.setParent(window)
        self.parameters.committed.connect(self.accept)
        window.protocol.session_mode.currentTextChanged.connect(
            lambda value: self.parameters.set_closed_loop(value == "Closed-loop")
        )
        self.parameters.set_closed_loop(
            window.protocol.session_mode.currentText() == "Closed-loop"
        )
        self.set_program(blank_program())

    def accept(self, program):
        self.program = program
        self.parameters.program = program

    def set_program(self, program):
        self.program = program
        self.parameters.bind(program, (0,), 0 if program.sequence[0].settings else -1)

    def add_stimulus(self, preset):
        from cephvr.gui.stimulus_presets import add_stimulus

        program = add_stimulus(self.program, (0,), preset, ("Left", "Right"))
        self.program = program
        self.parameters.bind(program, (0,), len(program.sequence[0].settings) - 1)

    def remove_stimulus(self):
        from cephvr.gui.stimulus_presets import remove_stimulus

        self.set_program(
            remove_stimulus(self.program, (0,), self.parameters.layer_index)
        )
