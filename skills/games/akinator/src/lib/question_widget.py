from bridges.python.src.sdk.widget import WidgetOptions
from ..widgets.number_widget import NumberWidget, NumberWidgetParams

number_widget_options: WidgetOptions[NumberWidgetParams] = WidgetOptions(
    params={'random_number': random_number}
)
number_widget = NumberWidget(number_widget_options)
