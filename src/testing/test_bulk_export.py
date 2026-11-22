import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.gui.bulk_export import export_models, models_newest_first
from src.importers import CsvImporter


class BulkExportTests(unittest.TestCase):
    """Test bulk export."""
    def test_validation_failures_skip_and_progress(self):
        """Check validation failures skip and progress."""
        good = Mock(path_name='Root::Good')
        good.validate_basemlm_integrity.return_value = []
        bad = Mock(path_name='Root::Bad')
        bad.validate_basemlm_integrity.return_value = ['C12']
        broken = Mock(path_name='Root::Broken')
        broken.validate_basemlm_integrity.side_effect = ValueError('check failed')
        models = [SimpleNamespace(name=n, model=m) for n, m in [('Good', good), ('Bad', bad), ('Broken', broken)]]
        progress = Mock()
        with tempfile.TemporaryDirectory() as folder:
            results = export_models(models, folder, progress=progress)
            self.assertIsNone(results[0][2])
            self.assertIn('C12', results[1][2])
            self.assertIn('check failed', results[2][2])
            self.assertEqual(progress.call_args_list[-1].args, (3, 3))
            bad.export_xml.assert_not_called()
            results = export_models(models[1:], folder, skip_check=True)
            self.assertTrue(all(error is None for _, _, error in results))
            self.assertEqual(bad.validate_basemlm_integrity.call_count, 1)
            self.assertEqual(broken.validate_basemlm_integrity.call_count, 1)

    def test_real_xml_exports_avoid_existing_and_duplicate_names(self):
        """Check real xml exports avoid existing and duplicate names."""
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, 'source.csv')
            source.write_text('name,age\nAlice,22\n', encoding='utf-8')
            model, _ = CsvImporter().import_file(str(source))
            existing = Path(folder, 'Sample.xml')
            existing.write_text('keep', encoding='utf-8')
            models = [SimpleNamespace(name='Sample', model=model), SimpleNamespace(name='sample', model=model)]
            results = export_models(models, folder, skip_check=True)
            self.assertTrue(all(error is None for _, _, error in results), results)
            self.assertEqual(existing.read_text(encoding='utf-8'), 'keep')
            self.assertEqual([Path(path).name for _, path, _ in results], ['Sample (2).xml', 'sample (3).xml'])
            self.assertTrue(all(Path(path).is_file() for _, path, _ in results))

    def test_export_exception_does_not_stop_other_models(self):
        """Check export exception does not stop other models."""
        first = Mock(path_name='Root::A')
        first.export_xml.side_effect = OSError('disk full')
        second = Mock(path_name='Root::B')
        with tempfile.TemporaryDirectory() as folder:
            results = export_models([SimpleNamespace(name='A', model=first), SimpleNamespace(name='B', model=second)], folder, True)
        self.assertIn('disk full', results[0][2])
        self.assertIsNone(results[1][2])

    def test_newest_first_and_unknown_last(self):
        """Check newest first and unknown last."""
        def model(name, worked='', uploaded=''):
            return SimpleNamespace(name=name, last_worked_on=worked, uploaded=uploaded)
        models = [model('old', '2023-01-01 10:00'), model('unknown'), model('new', '2025-02-02 09:00'),
                  model('fallback', uploaded='2024-01-01 00:00')]
        self.assertEqual([m.name for m in models_newest_first(models)], ['new', 'fallback', 'old', 'unknown'])


if __name__ == '__main__':
    unittest.main()
