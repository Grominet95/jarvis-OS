from ..widget_component import WidgetComponent


class Button(WidgetComponent[dict]):
    def __init__(self, props: dict):
        super().__init__(props)
