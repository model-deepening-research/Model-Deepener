import pickle
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from src.gui.app import ModelDeepenerApp
from src.importers.plantuml_import.plantuml_importer import PlantUmlImporter
from src.importers.ecore_import.ecore_importer import EcoreImporter
from src.basemlm.basemlm_model import BaseMlmModel
from src.importers.class_diagram import ClassDiagram, UmlAttribute, EXACTLY_ONE
from src.importers.class_diagram_builder import ClassDiagramBuilder
from src.importers.import_report import ImportAdaptation, ImportReport


class ElementNotesTests(unittest.TestCase):
    def test_notes_follow_element_and_survive_pickle(self) -> None:
        diagram = ClassDiagram('Example')
        item = diagram.get_or_create_class('Baby Clothing')
        item.add_attribute(UmlAttribute('Name', 'String', EXACTLY_ONE))
        diagram.add_adaptation('Interface', 'Baby Clothing', 'Imported as abstract.')
        model = BaseMlmModel()
        ClassDiagramBuilder().build(model, diagram)
        obj = pickle.loads(pickle.dumps(model)).get_objects()[0]
        self.assertIn(('Baby Clothing → BabyClothing', False), obj.get_import_notes())
        self.assertIn(('Imported as abstract.', False), obj.get_import_notes())
        self.assertIn(('Name → name', False), obj.get_regular_attributes()[0].get_import_notes())

    def test_serious_type_problem_is_recorded_on_attribute(self) -> None:
        model, _ = PlantUmlImporter().import_file('models/plantuml/TransportCompany.txt')
        vehicle = next(obj for obj in model.get_objects() if obj.name == 'Vehicle')
        attribute = next(attr for attr in vehicle.get_regular_attributes() if attr.name == 'type')
        self.assertTrue(any(serious and 'VehicleType' in text for text, serious in attribute.get_import_notes()))
        self.assertFalse(any('VehicleType' in text for text, _ in vehicle.get_import_notes()))
        self.assertEqual(ModelDeepenerApp._import_note_tag(attribute), 'serious_adaptation')

    def test_generated_names_and_table_elements_are_recorded(self) -> None:
        model, _ = EcoreImporter().import_file('models/ecore/accounting__accounting.ecore')
        association = model.get_associations()[0]
        self.assertTrue(any('Association name assigned' in text for text, _ in association.get_import_notes()))
        ends = (association.get_source_association_end(), association.get_target_association_end())
        self.assertTrue(any(end.get_import_notes() for end in ends))
        ui = SimpleNamespace(current_model=model, _associations_for_class=ModelDeepenerApp._associations_for_class,
                             _inherited_associations=lambda obj: [], _association_table_row=lambda assoc: (assoc.name, '', '', ''),
                             _render_detail_table=Mock(), ASSOCIATION_TABLE_HEADERS=('Name', 'Source', 'Target', 'Multiplicity'))
        ModelDeepenerApp._render_class_association_table(ui, association.source_object)
        self.assertEqual(ui._render_detail_table.call_args.kwargs['highlight_column'], 3)
        elements = ui._render_detail_table.call_args.kwargs['cell_elements']
        self.assertTrue(any(cells[0] == (association, 'name') for cells in elements))
        self.assertTrue(any(cells[1] == (ends[1], 'name') and cells[2] == (ends[0], 'name') for cells in elements))

    def test_attribute_field_notes_are_separate_and_inherited_rows_unmarked(self) -> None:
        model, _ = PlantUmlImporter().import_file('models/plantuml/TransportCompany.txt')
        vehicle = next(obj for obj in model.get_objects() if obj.name == 'Vehicle')
        attribute = next(attr for attr in vehicle.get_regular_attributes() if attr.name == 'type')
        self.assertTrue(any('Type' in text and not serious for text, serious in attribute.get_import_notes_for('name')))
        self.assertTrue(any('VehicleType' in text and serious for text, serious in attribute.get_import_notes_for('type')))
        self.assertEqual(attribute.get_import_notes_for('multiplicity'), [])

        model, _ = PlantUmlImporter().import_file('models/plantuml/HelpingHands.txt')
        food = next(obj for obj in model.get_objects() if obj.name == 'FoodItem')
        parent = next(obj for obj in model.get_objects() if obj.name == 'Item')
        render = Mock()
        ui = SimpleNamespace(_all_parent_classes=lambda _obj: [parent], _render_detail_table=render)
        ModelDeepenerApp._render_class_attribute_table(ui, food)
        cells = render.call_args.kwargs['cell_elements']
        self.assertTrue(parent.get_regular_attributes())
        self.assertTrue(all(cell == [None, None, None, None] for cell in cells[-len(parent.get_regular_attributes()):]))
        self.assertNotIn('muted_row_indexes', render.call_args.kwargs)

    def test_enumeration_literal_note_is_specific_and_persistent(self) -> None:
        model, _ = PlantUmlImporter().import_file('models/plantuml/HelpingHands.txt')
        enum = next(item for item in model.get_enum_types() if item.name == 'ItemCategory')
        enum = pickle.loads(pickle.dumps(enum))
        notes = enum.get_import_notes_for('value:BabyClothing')
        self.assertEqual(notes, [('Baby Clothing \u2192 BabyClothing', False)])
        self.assertNotIn(notes[0], enum.get_import_notes_for('name'))
        render = Mock()
        ui = SimpleNamespace(_clear_detail_option_bar=Mock(), detail_title=Mock(), detail_subtitle=Mock(),
                             _render_detail_table=render)
        ModelDeepenerApp._render_enum_details(ui, enum)
        rows = render.call_args.args[1]
        cells = render.call_args.kwargs['cell_elements']
        index = next(i for i, row in enumerate(rows) if row[1] == 'BabyClothing')
        self.assertEqual(cells[index][1], (enum, 'value:BabyClothing'))

    def test_detail_columns_start_at_original_fixed_widths(self) -> None:
        self.assertEqual(ModelDeepenerApp._standard_detail_column_widths(4), [220, 170, 170, 170])
        self.assertEqual(ModelDeepenerApp._standard_detail_column_widths(4, [110, 180, 150, 520]),
                         [110, 180, 150, 520])
        self.assertEqual(ModelDeepenerApp._standard_detail_column_widths(3, [300]), [300, 170, 170])

    def test_boundary_drag_changes_only_adjacent_columns(self) -> None:
        move = ModelDeepenerApp._move_column_boundary
        self.assertEqual(move([220, 170, 170, 170], 1, 30), [220, 200, 140, 170])
        self.assertEqual(move([220, 170, 170, 170], 1, -40), [220, 130, 210, 170])
        self.assertEqual(move([220, 170, 170, 170], 1, 1000), [220, 280, 60, 170])
        self.assertEqual(move([220, 170, 170, 170], 1, -1000), [220, 60, 280, 170])
        self.assertEqual(move([220, 170, 170, 170], 3, 50), [220, 170, 170, 170])

    def test_detail_drag_preserves_total_and_stores_widths(self) -> None:
        canvas = Mock()
        canvas.bbox.return_value = (0, 0, 730, 100)
        table = Mock()
        ui = SimpleNamespace(_detail_column_widths=[220, 170, 170, 170],
                             _detail_width_key=('detail', ('Attribute', 'Type', 'Multiplicity', 'Level')),
                             _table_column_widths={}, _move_column_boundary=ModelDeepenerApp._move_column_boundary,
                             detail_table=table, detail_canvas=canvas,
                             _update_detail_x_scrollbar_visibility=Mock())
        ModelDeepenerApp._start_detail_column_resize(ui, SimpleNamespace(x_root=100), 1)
        ModelDeepenerApp._resize_detail_column(ui, SimpleNamespace(x_root=130))
        self.assertEqual(ui._detail_column_widths, [220, 200, 140, 170])
        self.assertEqual(sum(ui._detail_column_widths), 730)
        self.assertEqual(table.grid_columnconfigure.call_count, 2)
        ModelDeepenerApp._finish_detail_column_resize(ui)
        self.assertEqual(ui._table_column_widths[ui._detail_width_key], [220, 200, 140, 170])
        self.assertEqual(ModelDeepenerApp._fit_column_widths(ui._table_column_widths[ui._detail_width_key], 730),
                         [220, 200, 140, 170])

    def test_width_fitting_fills_layout_and_respects_minimum(self) -> None:
        fit = ModelDeepenerApp._fit_column_widths
        for total in (240, 500, 1000):
            result = fit([220, 170, 170, 170], total)
            self.assertEqual(sum(result), total)
            self.assertTrue(all(width >= 60 for width in result))
        self.assertEqual(fit([200, 100, 90], 390), [200, 100, 90])
        self.assertEqual(fit([100, 100, 100], 100), [60, 60, 60])

    def test_severity_classification_is_shared(self) -> None:
        report = ImportReport()
        for kind, serious in [('Interface', False), ('Unknown type', True)]:
            item = ImportAdaptation(kind, '', kind)
            self.assertEqual(report.is_serious_adaptation(item), serious)
        self.assertEqual(BaseMlmModel().get_objects(), [])


if __name__ == '__main__':
    unittest.main()
