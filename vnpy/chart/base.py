from vnpy.trader.ui import QtGui


WHITE_COLOR = (255, 255, 255)
BLACK_COLOR = (0, 0, 0)
GREY_COLOR = (100, 100, 100)

# Up = red, Down = green — the HK/mainland convention futu 牛牛 / uSMART
# and other Chinese-market broker apps use. vnpy's stock default was
# up-red / down-CYAN; the cyan is the one thing that doesn't match those
# apps, so down is green here. Up stays the same bright red.
UP_COLOR = (255, 75, 75)
DOWN_COLOR = (55, 200, 120)
CURSOR_COLOR = (255, 245, 162)

PEN_WIDTH = 1
BAR_WIDTH = 0.3

AXIS_WIDTH = 0.8
NORMAL_FONT = QtGui.QFont("Arial", 9)


def to_int(value: float) -> int:
    """"""
    return int(round(value, 0))
