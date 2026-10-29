"""
Provides structure for precedence graphs, required for property-precedence analysis.
The precedence graph is a directed graph, with the direction a -> b expressing reverse precedence (i.e., b < a)
This allows interpreting the topological order of the graph as instantiation levels.
"""
import datetime
import os.path
from graphlib import TopologicalSorter

import networkx as nx
import pydot
from networkx import DiGraph

from src.model_deepening.image_file_format_enum import ImageFileFormat
from src.basemlm.basemlm_property import BaseMlmProperty
from src.basemlm.model_property_enum import ModelPropertyEnum
from src.model_deepening.property_group import PropertyGroup


class PropertyPrecedenceGraph:
    """Property precedence graph used for property precedence analysis. The graph is implemented through an
    adjacency list via a dictionary. Additionally, a redundant list containing all edges is maintained.
    This is done in order to simplify the generation of graph images."""

    def __init__(self, assigned_object):
        self.assigned_object = assigned_object
        self.nodes: {} = {}
        self.edges: [] = []
        self.poly_property_groups: [PropertyGroup] = []  # used for quicker checks, items should be
        # property groups with at least 2 model properties
        self.pydot_graph = None
        self.nx_digraph: DiGraph = None
        self.property_type: ModelPropertyEnum = ModelPropertyEnum.UNDEFINED
        self.output_folder: str = "test_file_outputs"  # default folder used for generated images
        self.sub_folder_name: str = assigned_object.get_model_name()
        self.update_graph_counter = 0

    def _update_graph_adjacency_list(self, key: PropertyGroup, value: [], place: int = 0):
        """Helper operation to centralize self.nodes.update calls.
        Provides possibility to log each call for error tracing"""
        self.nodes.update({key: value})
        self.update_graph_counter += 1
        log_progress: bool = False
        if log_progress:
            print("\n" + str(self.update_graph_counter) + ".")
            print(f"{len(self.poly_property_groups)}--{self.poly_property_groups}")
            print(self.update_graph_counter)
            print(f"UPDATE from {place} {key}: {value}")

    def _add_property_precedence_to_graph(self, pg1: PropertyGroup, pg2: PropertyGroup):
        """All property groups received as input here should only include one model property"""
        assert len(pg1) == 1 and len(pg2) == 1, "Property groups, at this stage, must only include one model property"
        for poly_pg in self.poly_property_groups:
            if poly_pg.includes_model_property(pg1.get_model_properties()[0]):
                pg1 = poly_pg
                # if pg1 is already part of a shared pg, then the precedence may be duplicate
                if pg1 in self.nodes.keys():
                    if pg2 in self.nodes[pg1]:
                        return
            if poly_pg.includes_model_property(pg2.get_model_properties()[0]):
                # if pg2 is already part of a shared pg, the precedence must have been added already
                pg2 = poly_pg
                return
        if pg1 in self.nodes:
            current_connections: [] = self.nodes.get(pg1)
            current_connections.append(pg2)
            self._update_graph_adjacency_list(pg1, current_connections, place=1)
        else:
            self._update_graph_adjacency_list(pg1, [pg2], place=2)
        if pg2 not in self.nodes:
            #  pg2 is also added as a node to the adjacency list so that every node can be accessed by traversing the
            # keys of the self.nodes dict
            self._update_graph_adjacency_list(pg2, [], place=3)
        #  self.edges.append((pg1, pg2))

    def _update_property_group(self, key, old_pg_groups: [PropertyGroup], new_p_group: PropertyGroup):
        """This function is primarily used in order to update connected nodes kept in value lists of the self.nodes
        dictionary. The update shall aggregate property groups as required."""
        connections: [] = self.nodes.get(key)
        pg_updated: bool = False
        for pg in connections:
            if pg in old_pg_groups:
                self.nodes[key].remove(pg) # note that 'remove' exits after first occurrence, but shouldn't be a problem
                if not pg_updated:
                    connections.append(new_p_group)
                    pg_updated = True

    def _update_shared_property_group(self, pg1: PropertyGroup, pg2: PropertyGroup):
        """This operation is called when two property groups are detected to be concormitant and should thus be
        part of a shared property group. In this case (i) all existing keys containing either pg must be updated to
        the shared pg and (ii) all values containing either pg must be updated to the shared pg.

        The property groups received here as inputs are always single-property groups. Thus, it must be checked whether
        the contained properties are already part of other poly-property groups.
        """

        found_pg1_key: bool = False
        found_pg2_key: bool = False
        pg1_in_poly_pg: bool = False
        pg2_in_poly_pg: bool = False
        shared_prop_group: PropertyGroup = PropertyGroup()
        shared_prop_group.merge_other_property_groups(pg1, pg2)
        prop_connections: [] = []  # used to update keys

        #  Step1 : check for poly-property groups
        for poly_pg in self.poly_property_groups:
            poly_pg_properties = poly_pg.get_model_properties()
            #  print(f"POLY PG {pg1} OR {pg2} in {poly_pg}")
            pg1_in_poly_pg = False
            pg2_in_poly_pg = False
            #  print(f"{pg1.get_model_properties()}")
            if pg1.get_model_properties() in poly_pg:
                pg1_in_poly_pg = True
            if pg2.get_model_properties() in poly_pg:
                #  print(f"FOUND: {pg1} and {pg2} in {poly_pg}")
                pg2_in_poly_pg = True
            #  print(f"PG1 {pg1_in_poly_pg}, PG2 {pg2_in_poly_pg}")
            if pg1_in_poly_pg and pg2_in_poly_pg:
                #  print(f"BOTH IN A POLY-PG {pg1} and {pg2}")
                #  print(f"--Is{shared_prop_group} is {poly_pg}?")
                if shared_prop_group != poly_pg:
                    shared_prop_group.merge_other_property_groups(poly_pg)  # TODO AVOID DUPLICATES IF POLY_PG SUPERSET
            else:
                if pg1_in_poly_pg or pg2_in_poly_pg:
                    shared_prop_group: PropertyGroup = PropertyGroup()
                    if pg1_in_poly_pg:
                        shared_prop_group.merge_other_property_groups(poly_pg, pg2)
                    if pg2_in_poly_pg:
                        shared_prop_group.merge_other_property_groups(poly_pg, pg1)

        #  Step 2: check nodes
        key_to_update: PropertyGroup = PropertyGroup()
        for key in self.nodes:
            if pg1.get_model_properties() in key:
                found_pg1_key = True
                key_to_update = key
            if pg2.get_model_properties() in key:
                found_pg2_key = True
                key_to_update = key
        if found_pg1_key or found_pg2_key:  # consequently, key_to_update is set
            prop_connections.append(self.nodes[key_to_update])
            #  print(f"PROP HERE: {prop_connections}")
            if any(isinstance(item, list) for item in prop_connections):
                prop_connections = prop_connections[0]
            #  print(f"SHARED UPGRADE {key_to_update}: {prop_connections} OR {shared_prop_group}")
            #  print("\n------------------NOW WE UPDATE BECAUSE ONE IS INCLUDED -- BUT SHOULD WE")
            #  print(f"{pg1} pr {pg2} is in found in {key_to_update}, changed to {shared_prop_group}")
            if not (found_pg1_key and found_pg2_key):
                self.nodes.pop(key_to_update)
                self._update_graph_adjacency_list(shared_prop_group, prop_connections, place=4)
        else:  # if we get here, both pgs are not added as nodes yet and thus should be
            self._update_graph_adjacency_list(shared_prop_group, [], 6)  # key_to_update empty here
        self.poly_property_groups.append(shared_prop_group)

        #  Step 3: check values
        # HERE: regardless of whether they have already been keys, all values mentioning either p1 or p2 must be updated
        for key, values in self.nodes.items():
            #  TODO: values sometimes contains lists of lists (caused by what?) leading to errors here
            if pg1 in values or pg2 in values:
                #  TODO: may values not include more than pg1 and pg2? then, Shared-property_group must be expanded
                self._update_property_group(key=key, old_pg_groups=[pg1, pg2], new_p_group=shared_prop_group)

    def add_property_relation(self, prop1: BaseMlmProperty, prop2: BaseMlmProperty, rel_symbol: str):
        pg1: PropertyGroup = PropertyGroup(prop1)
        pg2: PropertyGroup = PropertyGroup(prop2)
        #  print(f"We add the following: {pg1} {rel_symbol} {pg2}")
        # This always creates new property groups even if identical in content!!!
        # Thus, changed equality operator for model properties
        match rel_symbol:
            case "<" | "<=":
                self._add_property_precedence_to_graph(pg1, pg2)
            case ">" | ">=":
                self._add_property_precedence_to_graph(pg2, pg1)
            case "=":
                self._update_shared_property_group(pg1, pg2)
            case "?":
                return  # ignore for now
            case "||":
                return # disjoint sets, can be ignored
            case _:
                raise ValueError(f"Unrecognized attribute relation: {rel_symbol}. Precedence graph couldn't be updated")

    def get_static_order(self) -> ():
        top_sorter: TopologicalSorter = TopologicalSorter(self.nodes)
        return tuple(top_sorter.static_order())

    def init_nx_graph(self):
        if self.nx_digraph is None:
            self.nx_digraph = nx.DiGraph(self.edges)

    def get_topological_generations(self) -> []:
        self.init_nx_graph()
        return [sorted(generation) for generation in nx.topological_generations(self.nx_digraph)]

    def export_graph_as_image(self, graph_name: str, file_format: ImageFileFormat):
        self._add_all_edges_to_edges_list()
        if not len(self.edges) > 0:
            #  nothing to generate
            return
        else:
            if self.pydot_graph is None:
                self.create_pydot_graph()
            self._create_sub_folder()
            match file_format:
                case ImageFileFormat.PNG:
                    self.pydot_graph.write_png(
                        os.path.join(self.output_folder, self.sub_folder_name,
                                     self._get_image_file_name(graph_name, "png")))
                case ImageFileFormat.SVG:
                    self.pydot_graph.write_svg(
                        os.path.join(self.output_folder, self.sub_folder_name,
                                     self._get_image_file_name(graph_name, "svg")))
                case _:
                    raise ValueError(f"Unrecognized file format {file_format}. Image not generated")

    def _create_sub_folder(self):
        try:
            if not os.path.exists(os.path.join(self.output_folder, self.sub_folder_name)):
                os.makedirs(os.path.join(self.output_folder, self.sub_folder_name))
        except OSError:
            print('Error: Creating directory ' + os.path.join(self.output_folder, self.sub_folder_name))

    def _get_image_file_name(self, graph_name: str, format: str) -> str:
        today = datetime.datetime.now()
        time_str: str = f"{today.year}{today.month}{today.day}"
        suffix: int = 1
        filename: str = f"{graph_name}_{self.property_type.value}PrecedenceGraph_v{time_str}-v{str(suffix)}.{format}"
        while os.path.exists(os.path.join(self.output_folder, self.sub_folder_name, filename)):
            suffix += 1
            filename = f"{graph_name}_{self.property_type.value}PrecedenceGraph_v{time_str}-v{str(suffix)}.{format}"
        return filename

    def create_pydot_graph(self):
        self.pydot_graph = pydot.Dot("Precedence Graph", graph_type='digraph')
        self._transitive_reduction()
        for pg_node in self.nodes.keys():
            self.pydot_graph.add_node(pydot.Node(pg_node.get_print_name()))
            #  print(f"PYDOT added NODE: {pg_node.get_print_name()}")
        for edge in self.edges:
            self.pydot_graph.add_edge(pydot.Edge(edge[0].get_print_name(), edge[1].get_print_name()))
            #  print(f"PYDOT added EDGE: {edge[0].get_print_name()} TO {edge[1].get_print_name()}")

    def _add_all_edges_to_edges_list(self):
        if len(self.edges) == 0:
            for node in self.nodes:
                for value in self.nodes[node]:  # values should always be a list
                    self.edges.append((node, value))

    def _remove_edge(self, mp1: BaseMlmProperty, mp2: BaseMlmProperty):
        """This helper function only removes edges from the redundant edges list. This is done to support
        transitive reduction of PyDot Graphs, which visualize the edges in this list"""
        edge = (mp1, mp2)
        try:
            self.edges.remove(edge)
        except:
            print(f"FAILED TO REMOVE EDGE {(mp1, mp2)}")

    def _transitive_reduction(self):
        """Transitive reduction algorithm used only for edges list and thus only concerns graph visualization"""
        for x in self.nodes.keys():
            for y in self.nodes.keys():
                for z in self.nodes.keys():
                    if (x, y) in self.edges and (y, z) in self.edges and (x, z) in self.edges:
                        self._remove_edge(x, z)

    def __repr__(self):
        rs: str = f"[{self.property_type.value.upper()} PRECEDENCE GRAPH]\n"
        for node, conns in self.nodes.items():
            rs += f"\t{node}: {conns}\n"
        return rs

    def return_edges_for_print(self):
        self._add_all_edges_to_edges_list()
        rs: str = f"[{self.property_type.value.upper()} PRECEDENCE GRAPH EDGES]\n"
        for edge in self.edges:
            rs += f"\tEdge From {edge[0]} to {edge[1]}\n"
        return rs
