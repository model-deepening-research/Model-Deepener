from __future__ import annotations

import xml.etree.ElementTree as ET


def preamble(project_name):
    """
    Creates the empty XModeler document that receives the exported model.

    Imports can later be copied from the source XML. Model receives classes,
    objects, attributes, and relationships. Instances and Edges hold the
    visible blocks and connections. Display settings use XModeler's structure.
    """

    root = ET.Element('XModelerPackage', path=project_name, version='4')

    ET.SubElement(root, 'Imports')
    ET.SubElement(root, 'Model', name=project_name)
    
    diagrams = ET.SubElement(root, 'Diagrams')
    diagram = ET.SubElement(diagrams, 'Diagram', name='FmmlxDiagram_1', umlMode='false')

    ET.SubElement(diagram, 'Instances')
    ET.SubElement(diagram, 'Edges')
    diagram_display_properties = ET.SubElement(diagram, 'DiagramDisplayProperties')
    display_settings = {
        'SLOTS': 'true',
        'CONCRETESYNTAX': 'true',
        'METACLASSNAME': 'false',
        'ISSUETABLE': 'false',
        'OPERATIONS': 'true',
        'DERIVEDATTRIBUTES': 'true',
        'CONSTRAINTS': 'true',
        'CONSTRAINTREPORTS': 'true',
        'DERIVEDOPERATIONS': 'true',
        'OPERATIONVALUES': 'true',
        'GETTERSANDSETTERS': 'true',
    }
    for setting_name, setting_value in display_settings.items():
        setting = ET.SubElement(diagram_display_properties, setting_name)
        setting.text = setting_value
    ET.SubElement(diagram, 'Notes')
    views = ET.SubElement(diagram, 'Views')
    ET.SubElement(views, 'View', name='Main View', tx='0.0', ty='0.0', xx='1.0')
    
    return root


def writeXML(root: ET.Element, filepath: str):
    """Writes a readable UTF-8 XML file with an explicit XML declaration."""
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(filepath, encoding="utf-8", xml_declaration=True)
