"""Image export utilities."""

from wtp_autolayout.visualization import LayoutRenderer


class ImageExporter:
    """Export layout images."""

    def __init__(self, renderer=None):
        self.renderer = renderer or LayoutRenderer()

    def export_png(self, layout, output_path, title=None) -> str:
        return self.renderer.save_png(layout, output_path, title=title)
