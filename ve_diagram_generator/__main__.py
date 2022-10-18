import re
from os import path, environ
from pathlib import Path
from pprint import pformat
import collections
import argparse
import textwrap

import opl
import rdflib
from lxml.html import document_fromstring

from . import __version__, ve_patterns, method_registry, View, DirectedView, MacroNotFoundException, Table, Tooltip, Diagram

from .view import _promote_directive_page_title

PD_ASSET = path.join(Path(__file__).parent.absolute(), 'asset')

P_INCQUERY_SERVER = environ.get('INCQUERY_SERVER') or g_args.incquery_server
S_INCQUERY_USER = environ.get('INCQUERY_USER')
S_INCQUERY_PASS = environ.get('INCQUERY_PASS')

P_CONFLUENCE_SERVER = environ.get('CONFLUENCE_SERVER') or g_args.confluence_server
S_CONFLUENCE_USER = environ.get('CONFLUENCE_USER')
S_CONFLUENCE_PASS = environ.get('CONFLUENCE_PASS')

P_SPARQL_ENDPOINT = environ.get('SPARQL_ENDPOINT') or g_args.sparql_endpoint


if not P_INCQUERY_SERVER:
    raise Exception('Must provide a URL for IncQuery server')

if not P_CONFLUENCE_SERVER:
    raise Exception('Must provide a URL for Confluence server')

if not P_SPARQL_ENDPOINT:
    raise Exception('Must provide a URL for SPARQL endpoint')


H_DIRECTIVE_COMMANDS = {
    'insertView': Table,
    'insertHover': Tooltip,
}

H_DIRECTIVE_PAGE_TITLE_PREFIXES = {
    '_View:': Table,
}

H_DIRECTIVE_LINK_HREF_PREFIXES = {
    f'https://${P_CONFLUENCE_SERVER}': Tooltip,
}

def _sparql_iri(s_value):
    return rdflib.URIRef(s_value).n3()

def _sparql_literal(s_value):
    return rdflib.Literal(s_value).n3()

def _sparql_iri_map(si_var_key, si_var_value, h_map):
    sx_values = '\n            '.join([f'({_sparql_literal(si_key)} {_sparql_iri(p_value)})' for (si_key, p_value) in h_map.items()])
    return _normalize_indent(f'''
        values (?{si_var_key} ?{si_var_value}) {{
            {sx_values}
        }}
    ''', '    ').strip()

def _inject(f_injector, a_inputs):
    return ' '.join([f_injector(s) for s in a_inputs])

def _normalize_indent(sx_input, s_indent):
    return textwrap.indent(textwrap.dedent(sx_input), s_indent)

y_parser = argparse.ArgumentParser(
    prog='ve_diagram_generator',
    description='render all views for the given set of pages',
)

# required options
y_parser.add_argument('-c', '--compartment-uri', help='IncQuery Compartment URI')
y_parser.add_argument('-m', '--mopid', help='MMS Org / Project ID (#ref)')
y_parser.add_argument('-p', '--page-id', action='append', help='Page ID(s)', required=True)
y_parser.add_argument('-s', '--space', help='Confluence Wiki space ID', required=True)

# optional options
y_parser.add_argument('--incquery-server')
y_parser.add_argument('--confluence-server')
y_parser.add_argument('--sparql-endpoint')

# parse args
g_args = y_parser.parse_args()

a_pages = g_args.page_id
si_space = g_args.space
p_space = f'{P_CONFLUENCE_SERVER}/display/{si_space}'

# incquery config
gc_incquery = {}

# compartment URI given
if 'compartment_uri' in g_args:
    gc_incquery['compartment'] = g_args.compartment_uri
# use mopid
elif 'mopid' in g_args:
    # extract parts
    m_mopid = re.match(r'^([^/]+)/([^#]+)(?:#(.*))?$', g_args.mopid)

    # update config
    gc_incquery.update({
        'org': m_mopid[1],
        'project': m_mopid[2],
        'ref': m_mopid[3] or None,
    })
# neither given
else:
    raise Exception('Must provide either a compartment URI [--compartment-uri] or MMS Org / Project ID (#ref) [--mopid] qualifier')



# create IncQuery instance
k_iqs = opl.IncQueryProject(
    **gc_incquery,
    server=P_INCQUERY_SERVER,
    username=S_INCQUERY_USER,
    password=S_INCQUERY_PASS,
    patterns={
        **opl.patterns['basic'],
        **ve_patterns,
    },
)

# create Confluence instance
k_confluence = opl.Confluence(
    server=P_CONFLUENCE_SERVER,
    username=S_CONFLUENCE_USER,
    password=S_CONFLUENCE_PASS,
)

# create SPARQL instance
k_sparql = opl.Sparql(
    endpoint=P_SPARQL_ENDPOINT,
)


def _render_table(kv_table: Table, si_page_src: str):
    g_template_ref = kv_table.template_ref

    p_ref = g_template_ref.iri

    if si_space != g_template_ref.space:
        raise Exception(f'Cross reference in #{si_page_src} invocates template definition in another space ["{si_space}" != "{g_template_ref.space}"]: <{p_ref}>')

    # load the SPARQL query and process vars/injections
    with open(path.join(PD_ASSET, 'view-table-def.rq'), 'r') as d:
        sq_template_def = opl.Sparql.load(
            template=d.read(),
            variables={
                'SPACE_GRAPH': p_space,
                'SOURCE_PAGE': p_ref,
            },
        )

    # execute query
    a_defs = k_sparql.fetch(sq_template_def)

    # build args from vars
    h_args = collections.defaultdict(list)
    for g_row in a_defs:
        si_key = g_row['param_key']['value']
        s_value = g_row['param_value']['value']

        # array value
        if 'param_value_is_array' in g_row:
            h_args[si_key].append(s_value)
        # text value
        else:
            h_args[si_key] = s_value

    # ref viewpoint method id
    si_method = h_args['templateType']

    # template type was not given
    if isinstance(si_method, list):
        raise Exception(f'The required "templateType" field is missing from the view template table defined at <{p_ref}>')

    # method does not exist in registry
    if si_method not in method_registry:
        raise Exception(f'"{si_method}" was not found in the method registry')

    # evaluate viewpoint method
    k_result = method_registry[si_method](k_iqs, h_args)

    # insert table as xref view and serialize XHTML document
    return kv_table.render(k_result)


def _insert_tooltip(g_tooltip, s_content):
    # Extract properties
    si_macro_id = g_tooltip['macro_id']['value']
    s_ref_type, s_ref_id = g_tooltip['macro_class']['value'][len('insertHover-'):].split('.')

    # Execute query based on insertHover reference type and ID
    if s_ref_type == 'dng':
        s_ref_type = 'DNG'
        h_bindings = {
            'identifier': s_ref_id,
            'artifactShapeName': 'Requirement'
        }
    else:
        raise Exception(f'Unknown insertHover reference type {s_ref_type}')    
    a_rows = k_iqs.execute_query(h_queries['artifactInfo'], h_bindings)
    
    # Convert query result to tooltip
    if not a_rows:
        raise Exception(f'No information found for {s_ref_type} {s_ref_id}')
    h_row = a_rows[0]
    s_artifact_name = h_row['artifactName']
    s_primary_text = h_row['primaryText']
    s_artifact_url = h_row['artifactURL']
    return ced.set_tooltip(
        s_content,
        si_macro_id,
        f'{s_ref_type}, {s_ref_id}, {s_artifact_name}: {document_fromstring(s_primary_text).text_content()}',
        s_artifact_url
    )



def _render_directive(g_directive, sx_document: str, si_page_src: str):
    # explicit command is provided in an annotated span
    if 'directive_command' in g_directive:
        # ref command id
        si_command = g_directive['directive_command']['value']

        # lookup view class
        dc_view = H_DIRECTIVE_COMMANDS[si_command]

        # extract directive macro id
        si_macro = g_directive['directive_macro_id']['value']
    # directive page title
    elif 'directive_page_title_prefix' in g_directive:
        # ref page title prefix
        si_prefix = g_directive['directive_page_title_prefix']['value']

        # lookup view class
        dc_view = H_DIRECTIVE_PAGE_TITLE_PREFIXES[si_prefix]

        # promote inferred directive to command
        (si_macro, sx_document) = _promote_directive_page_title(g_directive, sx_document)
    # directive link href
    elif 'directive_link_href_prefix' in g_directive:
        # ref link href prefix
        si_prefix = g_directive['directive_link_href_prefix']['value']

        # lookup view class
        dc_view = H_DIRECTIVE_LINK_HREF_PREFIXES[si_prefix]

        # promote inferred directive to command
        (si_macro, sx_document) = _promote_directive_link(g_directive, sx_document)
    # none
    else:
        raise Exception(f'A directive was matched in the SPARQL query that is not routable to a view:\n{pformat(g_directive)}')

    # instantiate view
    k_view = dc_view(
        document=sx_document,
        directive_macro_id=si_macro,
        extras=g_directive,
    )

    # clear renders
    k_view.clear()

    # table
    if isinstance(k_view, Table):
        return _render_table(k_view, si_page_src)
    elif isinstance(k_view, Tooltip):
        return _render_tooltip(k_view, si_page_src)
    else:
        raise Exception(f'No route defined for view instance {k_view}')



def _render_all():
    # source page injection
    h_injection_source_page = {
        # when pages list is not empty, populate source values
        'SOURCE_PAGE': _normalize_indent(f'''
            values ?source_page_id {{
                {_inject(_sparql_literal, a_pages)}
            }}
        ''', '    ') if len(a_pages) else ''
    }

    # load the SPARQL query and process vars/injections
    with open(path.join(PD_ASSET, 'directives.rq'), 'r') as d:
        sq_directives = opl.Sparql.load(
            template=d.read(),
            variables={
                'SPACE_GRAPH': p_space,
            },
            injections={
                **h_injection_source_page,
                'DIRECTIVE_COMMANDS': _inject(_sparql_literal, H_DIRECTIVE_COMMANDS.keys()),
                'DIRECTIVE_PAGE_TITLE_PREFIXES': _inject(_sparql_literal, H_DIRECTIVE_PAGE_TITLE_PREFIXES.keys()),
                'DIRECTIVE_LINK_HREF_PREFIXES': _inject(_sparql_literal, H_DIRECTIVE_LINK_HREF_PREFIXES.keys()),
                'SPACES': _sparql_iri_map('space_id', 'space_iri', {
                    si_space: p_space,
                }),
            },
        )

    print(sq_directives)

    # group by page ID
    h_pages = collections.defaultdict(list)
    for g_directive in k_sparql.fetch(sq_directives):
        h_pages[g_directive['source_page_id']['value']].append(g_directive)

    # each page
    for si_page_src in h_pages:
        # create page handle
        k_page = k_confluence.page(si_page_src)

        # load page contents into memory
        s_content = k_page.get_content()

        # each directive
        for g_directive in h_pages[si_page_src]:
            s_content = _render_directive(g_directive, s_content, si_page_src)

        # update page content
        k_page.update_content(s_content)


_render_all()
