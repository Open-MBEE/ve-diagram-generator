import html
import uuid
from typing import NamedTuple, List, Dict

from opl import QueryResultsTable, QueryField

H_ARTIFACT_COMMON_DISPLAY_COLUMNS = {
    'identifier': 'ID',
    'artifactName': 'Requirement Name',
    'primaryText': 'Requirement Text',
    'keyDrivers': 'Key/Driver Indicator',
    'systems': 'Affected Systems',
    'maturity': 'Maturity',
}

SX_FIND_ARTIFACT_INFO = 'find artifactInfo('+','.join([
    'artifactName',
    'artifactId',
    'artifactURL',
    'artifactShapeName',
    'level',
    'identifier',
    'primaryText',
    'maturity',
    'attributeKey',
    'attributeValue',
])+');'


# wrap an HTML string with a confluence HTML macro
def _wrap_confluence_html_macro(sx_content: str, g_row: Dict[str, str]) -> str:
    return f'''
        <ac:structured-macro ac:name="html" ac:schema-version="1" ac:macro-id="{uuid.uuid4()}">
            <ac:plain-text-body>
                <![CDATA[{sx_content.replace(']]>', ']]]]><!CDATA[>')}]]>
            </ac:plain-text-body>
        </ac:structured-macro>
    '''


class _Args:
    def __init__(self, h_args):
        self._h_args = h_args

    def any(self, si_key):
        return self._h_args[si_key]

    def str(self, si_key):
        z_input = self._h_args[si_key]
        if not isinstance(z_input, str):
            raise Exception('Argument `'+si_key+'` is not a string')
        return z_input

    def list(self, si_key):
        z_input = self._h_args[si_key]
        if not isinstance(z_input, list):
            raise Exception('Argument `'+si_key+'` is not a list')
        return z_input

class View:
    def __init__(self, base, fields):
        self._si_base_query = base
        self._h_fields = fields

    def evaluate(self, incquery, bindings, patterns={}):
        k_incquery = incquery
        h_fields = self._h_fields

        # start with base query
        a_rows = k_incquery.execute(self._si_base_query, bindings=bindings, patterns=patterns)

        # each row
        for g_row in a_rows:
            # each field
            for si_field in h_fields:
                g_field = h_fields[si_field]

                # extend row dict
                g_row[si_field] = k_incquery.extend_row(g_row, g_field)

        return a_rows


class UnionResult(NamedTuple):
    bindings: Dict[str, str]
    name: str
    query: str


def combine_unions(s_name, h_multi_fields):
    a_sigs = []
    a_params = []
    a_unions = []
    h_bindings = {}

    i_array = 0

    # each multi field
    for si_field in h_multi_fields:
        a_values = h_multi_fields[si_field]

        # bind key
        si_binding_key = f'array{i_array}Key'
        a_params.append(si_binding_key)
        h_bindings[si_binding_key] = si_field

        # how many values
        nl_values = len(a_values)

        # update signature
        a_sigs.append(str(nl_values))

        # each value
        for i_value in range(nl_values):
            # append VQL fragment
            a_unions.append(f'''
                {{
                    {SX_FIND_ARTIFACT_INFO}

                    find artifactAttributeStringArray(artifactId, array{i_array}Key, array{i_array}Value{i_value});
                }}
            ''')

            # bind value
            si_binding_value = f'array{i_array}Value{i_value}'
            a_params.append(si_binding_value)
            h_bindings[si_binding_value] = a_values[i_value]

        # increment array index
        i_array += 1

    # struct
    return UnionResult(
        bindings=h_bindings,
        name=s_name+'_'+'_'.join(a_sigs),
        query=f'''
            (
                artifactName: String, artifactId: java String, artifactURL: String,
                artifactShapeName: String, level: String, identifier: String,
                primaryText: String, maturity: String,
                attributeKey: String, attributeValue: String,
                {', '.join([si+': String' for si in a_params])}
            )
        '''+' or '.join(a_unions),
    )


def by(si_key):
    return lambda g_row: {
        si_key: g_row[si_key],
    }

select_array_item_value = lambda g_row: g_row['itemValue']

by_artifact_id = by('artifactId')

def _req_by_level_attrstring(k_incquery, h_args, b_include_children=False, patterns=None):
    h_patterns = {**k_incquery._h_patterns, **(patterns or {})}
    k_args = _Args(h_args)

    h_fields = {
        'keyDrivers': QueryField(
            join=by_artifact_id,
            query='artifactAttributeStringArray',
            select=select_array_item_value,
            bindings={
                'attributeKey': 'Key/Driver [S]',
            },
        ),
        'systems': QueryField(
            join=by_artifact_id,
            query='artifactAttributeStringArray',
            select=select_array_item_value,
            bindings={
                'attributeKey': 'Specified Element',
            },
        ),
    }

    if b_include_children:
        h_fields['children'] = QueryField(
            join=by_artifact_id,
            query='artifactChildren',
            select=lambda g_row: g_row['childName'],
        )

    k_view = View(
        base='artifactInfo',
        fields=h_fields,
    )

    h_bindings = {
        **h_args,
        'level': k_args.str('level'),  # e.g., 'L3'
        'artifactShapeName': 'Requirement',
        'attributeKey': k_args.str('attributeKey'),  # h_args[''],  # e.g., 'System VAC'
        'attributeValue': k_args.str('attributeValue'),  # e.g., 'Sequencing'
    }

    a_rows = k_view.evaluate(k_incquery,
        bindings=h_bindings,
        patterns=patterns or {},
    )

    # copy dict from common
    h_display = {
        **H_ARTIFACT_COMMON_DISPLAY_COLUMNS,
    }

    # children included
    if b_include_children:
        # update display dict
        h_display.update({
            'children': 'Child Requirements',
        })

    # return new Result
    return QueryResultsTable(
        rows=a_rows,
        labels=h_display,
        rewriters={
            'primaryText': _wrap_confluence_html_macro,
            'artifactName': lambda z_value, g_row: '<a href="{url}">{value}</a>'.format(
                url=g_row['artifactURL'],
                value=html.escape(z_value),
            ),
        },
    )


def _req_system_vac(k_incquery, h_args, b_include_children):
    k_args = _Args(h_args)

    h_bindings = {
        'level': k_args.str('level'),  # e.g., 'L3'
        'attributeKey': 'System VAC',
        'attributeValue': k_args.str('functionalArea'),  # e.g., 'Sequencing'
    }

    z_maturity = k_args.any('maturity')
    a_maturities = []

    if isinstance(z_maturity, str) and z_maturity:
        a_maturities = [k_args.str('maturity')]
    elif isinstance(z_maturity, list):
        a_maturities = k_args.list('maturity')

    if len(a_maturities):
        if 1 == len(a_maturities):
            return _req_by_level_attrstring(k_incquery, {
                **h_bindings,
                'maturity': a_maturities[0],
            }, b_include_children)

        g_union =combine_unions(k_incquery._h_patterns['artifactInfo']+'Includes', {
            'Maturity': a_maturities,
        })

        h_bindings.update(g_union.bindings)

        breakpoint()
        raise Exception('dynamic disjunctive queries not yet implemented')
        si_query = k_incquery.define_query(g_union.name, g_union.query)

        return _req_by_level_attrstring(k_incquery, h_bindings, b_include_children, patterns={
            'artifactInfo': si_query,
        })

    else:
        return _req_by_level_attrstring(k_incquery, h_bindings, b_include_children)


def _system_reqs(k_incquery, h_args):
    return _req_system_vac(k_incquery, h_args, True)

def _subsystem_reqs(k_incquery, h_args):
    return _req_system_vac(k_incquery, h_args, False)

method_registry = {
    'Appendix Flight System Requirements': _system_reqs,
    'Appendix Subsystem Requirements': _subsystem_reqs,
}
