import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.gui.app import ModelDeepenerApp
from src.basemlm.basemlm_model import BaseMlmModel


class BatchMetricsTests(unittest.TestCase):
    """Test batch metrics."""
    def test_formats_and_half_up_means(self):
        """Check formats and half up means."""
        formats = ['XML', 'CSV', 'PLANTUML', 'UML-XMI', 'ECORE', '']
        models = [SimpleNamespace(name=f"Model {i}", file_type=kind, source_file='legacy.xmi' if not kind else '', model=i)
                  for i, kind in enumerate(formats)]
        ui = SimpleNamespace(_batch_format=ModelDeepenerApp._batch_format,
                             _display_file_type=ModelDeepenerApp._display_file_type,
                             _model_metrics=lambda model: [('Classes', 1 if model < 3 else 2),
                                                           ('Objects', 4 if model < 2 else 5)])
        counts, means, _headers, _rows = ModelDeepenerApp._prepare_batch_page(ui, models, lambda *_: None)
        self.assertEqual(dict(counts), {'Number of Models': 6, 'Number of FMMLx': 1, 'Number of CSV': 1,
                                        'Number of PlantUML': 1, 'Number of XMI': 2, 'Number of Ecore': 1})
        self.assertEqual(dict(means), {'Classes': 2, 'Objects': 5})
        _, below_half, _headers, _rows = ModelDeepenerApp._prepare_batch_page(ui, models[:3], lambda *_: None)
        self.assertEqual(dict(below_half)['Objects'], 4)

    def test_empty_batch(self):
        """Check empty batch."""
        ui = SimpleNamespace(_batch_format=ModelDeepenerApp._batch_format, _model_metrics=Mock())
        counts, means, _headers, _rows = ModelDeepenerApp._prepare_batch_page(ui, [], lambda *_: None)
        self.assertEqual(dict(counts)['Number of Models'], 0)
        self.assertEqual(means, [])
        ui._model_metrics.assert_not_called()

    def test_normal_metrics_have_no_operations_card(self):
        """Check normal metrics have no operations card."""
        model = BaseMlmModel()
        ui = SimpleNamespace(_count_higher_level_classes=ModelDeepenerApp._count_higher_level_classes,
                             _count_attributes=ModelDeepenerApp._count_attributes,
                             _count_generalizations=ModelDeepenerApp._count_generalizations,
                             _count_slots=ModelDeepenerApp._count_slots)
        labels = [name for name, _ in ModelDeepenerApp._model_metrics(ui, model)]
        self.assertEqual(labels, ['Higher Level Classes', 'Classes', 'Attributes', 'Enumeration Types',
                                  'Generalizations', 'Associations', 'Objects', 'Slots', 'Links'])


if __name__ == '__main__':
    unittest.main()
