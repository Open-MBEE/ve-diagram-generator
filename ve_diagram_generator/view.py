import abc
import re
import uuid
from typing import Dict, List, NamedTuple

from lxml import etree
from opl import QueryResultsTable


# type aliases
Hash = Dict[str, str]

# prefix to use for all generated view IDs
SI_VIEW_PREFIX = 've'

# root element tag
SI_ROOT = 'root_c0f292f94e924a3a98af22447fd3d3a2'

# unique namespaces prefix
P_URN_NS = 'urn:confluence-prefix:'

# set of prefixes to support when parsing XHTML strings from Confluence
AS_PREFIXES = {
    'ac',
    'ri',
}

# dict of namespaces to support from prefixes
H_NAMESPACES = {si_ns: f'{P_URN_NS}{si_ns}' for si_ns in AS_PREFIXES}

# prepare XHTML namespace declaration string
SX_NAMESPACES = ' '.join([f'xmlns:{si_ns}="{P_URN_NS}{si_ns}"' for si_ns in AS_PREFIXES])

# need to preserve CDATA when parsing XHTML
Y_LXML_PARSER = etree.XMLParser(strip_cdata=False)

# entity replacements hash
H_ENTITY_REPLACEMENTS = {
    '&nbsp;': '&#160;'
}


# produce a unique namespace for arbitrary XHTML tags having expected prefixes
def _lxml_ns(si_ns: str, s_local: str='') -> str:
    return '{'+P_URN_NS+si_ns+'}'+s_local


# parse a simple XHTML string into a wrapped lxml document
def _lxml_from_string(s_content: str):
    for s_entity, s_replace in H_ENTITY_REPLACEMENTS.items():
        s_content = s_content.replace(s_entity, s_replace)

    # wrap the content with a root node
    return etree.fromstring(f'<{SI_ROOT} {SX_NAMESPACES}>'+s_content+f'</{SI_ROOT}>', parser=Y_LXML_PARSER)


# convert a wrapped lxml document into a simple XHTML string
def _lxml_to_string(ye_root) -> str:
    # serialize entire document
    s_doc = etree.tostring(ye_root).decode()

    # remove dummy root element
    return re.sub(r'^\s*<'+SI_ROOT+r'[^>]*>\s*|\s*<\/'+SI_ROOT+r'>\s*$', '', s_doc)

def _expand_ns(sx_input):
    for si_ns in AS_PREFIXES:
        if sx_input.startswith(si_ns+':'):
            return sx_input.replace(si_ns+':', '{'+P_URN_NS+si_ns+'}', 1)
    return sx_input

# helper function for creating elements
def _element(tag: str, attrs: Hash={}, children=None, text=None):
    s_tag = tag
    h_attrs = attrs
    a_children = children
    s_text = text

    # create element
    ye_elmt = etree.Element(_expand_ns(s_tag), nsmap=H_NAMESPACES)

    # set each attribute
    for si_key in h_attrs:
        ye_elmt.set(_expand_ns(si_key), h_attrs[si_key])

    # has text
    if s_text is not None:
        ye_elmt.text = s_text
    # has children
    elif a_children is not None:
        for ye_child in a_children:
            ye_elmt.append(ye_child)

    # return element
    return ye_elmt

# helper function for creating elements with 'ac' prefix
def _ac_element(s_tag: str, h_attrs: Hash={}):
    # create element
    ye_elmt = etree.Element(_lxml_ns('ac', s_tag), nsmap=H_NAMESPACES)

    # set each attribute
    for si_key in h_attrs:
        ye_elmt.set(_lxml_ns('ac', si_key), h_attrs[si_key])

    # return element
    return ye_elmt

def _macro_param(s_name, s_value):
    return _element('ac:parameter', {
        'ac:name': s_name,
    }, text=s_value)

def _span(id=None, class_name=None, hidden=False, body=None):
    s_id = id
    s_class = class_name
    b_hidden = hidden
    a_body = body or []

    a_children = []

    if b_hidden is True:
        a_children.append(_macro_param('style', text='display:none'))

    if s_class is not None:
        a_children.append(_macro_param('class', s_class))

    if s_id is not None:
        a_children.append(_macro_param('id', s_id))

    # create new macro uuid
    si_macro = str(uuid.uuid4())

    # construct element and return tuple
    return (si_macro, _element('ac:structured-macro', {
        'ac:name': 'span',
        'ac:schema-version': '1',
        'ac:macro-id': si_macro
    }, children=a_children+[
        _element('ac:parameter', {
            'ac:name': 'atlassian-macro-output-type',
        }, text='INLINE'),
        _element('ac:rich-text-body', children=a_body
            # [
            #     _element('p', children=a_body),
            # ]
        ),
    ]))


# promote an inferred page title directive to an annotated span
def _promote_directive_page_title(g_directive, sx_document: str):
    si_page = g_directive['directive_page_id']['value']

    # parse document
    ye_root = _lxml_from_string(sx_document)

    # extract page title from directive bindings
    si_title = g_directive['directive_page_title']['value'].replace('"', '')

    # narrow results so we replace correct link
    sx_filter = ''
    if 'directive_link_text' in g_directive:
        s_text = g_directive['directive_link_text']['value']
        # cannot match with quote in xpath query
        if '"' not in s_text:
            sx_filter += f'[following-sibling::ac:plain-text-link-body[text()="{s_text}"]]'

    # prepare xpath query
    si_space = g_directive['space_id']['value']
    sx_space = f'[not(@ri:space-key) or @ri:space-key="{si_space}"]'
    sx_content_title = f'[@ri:content-title="{si_title}"]'
    sx_id_param = f'ac:parameter[@ac:name="id"][starts-with(text(),"{SI_VIEW_PREFIX}-")]'
    sx_naked = f'[not(ancestor::ac:structured-macro[@ac:name="span"][child::{sx_id_param}])]'
    sx_xpath = f'.//ri:page{sx_space}{sx_content_title}{sx_naked}{sx_filter}'

    # evaluate xpath to find directive
    a_refs = ye_root.xpath(sx_xpath, namespaces=H_NAMESPACES)

    # no matching elements found
    if 0 == len(a_refs):
        raise Exception(f'could not find page reference using XPath `{sx_xpath}`')

    # take first match
    ye_ref = a_refs[0]

    # nav to parent
    ye_directive = ye_ref.getparent()
    
    # build structured macro element
    (si_macro, ye_command) = _span(
        class_name='insertTable',
        body=[
            _element('p', children=list(
                _lxml_from_string(_lxml_to_string(ye_directive)),
            )),
        ],
    )

    # replace the directive with the structured macro
    ye_directive.getparent().replace(ye_directive, ye_command)

    # reserialize document
    sx_output = _lxml_to_string(ye_root)

    # return macro id and output as tuple
    return (si_macro, sx_output)


# promote an inferred directive link to an annotated span
def _promote_directive_link(g_directive, sx_document: str):
    return ('N/A', sx_document)


class View(metaclass=abc.ABCMeta):
    '''
    A 'view' refers to the abstract collection of (user input, rendered element).
    A view 'directive' is the user input as it exists in the document.
    A view 'render' is the rendered element that is a result of evaluating the
        user input against a predefined dataset.
    '''
    def __init__(self, document: str, view_id: str=None):
        '''
        Create a View object for manipulating elements within a Confluence XHTML document

        :param document: the Confluence XHTML document
        :param view_id: the unique ID of the view if referencing an existing view
            or None/ommitted to create a new view
        '''
        sx_document = document
        try:
            self._ye_root = _lxml_from_string(sx_document)
        except etree.XMLSyntaxError:
            print(f'XML Syntax Error in document: """\n{sx_document}\n"""')
            raise
        except:
            raise

        self._si_view = view_id or uuid.uuid4().hex


    # view id prefix string
    def _prefix(self, a_append: List[str]=[]) -> str:
        return SI_VIEW_PREFIX+''.join(['-'+s for s in a_append])

    # generate a local id using overridable prefix
    def _local_id(self, *args) -> str:
        return self._prefix(list(args))

    def clear(self):
        '''
        Clear any existing renders belonging to this view
        '''
        # find any existing rendered view renders if they exists
        a_renders = self._ye_root.xpath('.//ac:parameter[@ac:name="id"][text()="{span_id}"]/..'.format(
            span_id=self._local_id('render')+'-'+self._si_view
        ), namespaces=H_NAMESPACES)

        # remove all of them
        for ye_render in a_renders:
            ye_render.getparent().remove(ye_render)

    def _insert(self, _ye_render) -> str:
        # insert view render element at the top of the page
        self._ye_root.insert(0, _ye_render)

        # return modified content
        return _lxml_to_string(self._ye_root)


class MacroNotFoundException(Exception):
    '''
    A macro having the given ID was not found in the document
    '''
    pass


class DirectedView(View, metaclass=abc.ABCMeta):
    def __init__(self, document: str, directive_macro_id: str, extras: Dict[str, Hash]={}):
        '''
        Create a View object for manipulating elements within a Confluence XHTML document

        :param document: the Confluence XHTML document
        :param directive_macro_id: the globally unique macro id of the view's directive
        '''
        si_macro = directive_macro_id

        # construct super
        super().__init__(document)

        # find view directive
        self._ye_directive = self._ye_root.find(f'.//ac:structured-macro[@ac:macro-id="{si_macro}"]', H_NAMESPACES)

        # macro does not exist
        if self._ye_directive is None:
            raise MacroNotFoundException(f'{self.__class__.__name__} macro with the id "{si_macro}" was not found in the given document; likely the Confluence wiki page and the RDF graph are out of sync')

        # deduce directive id if one exists
        a_xpaths = self._ye_directive.xpath('./ac:parameter[@ac:name="id"]/text()', namespaces=H_NAMESPACES)
        if a_xpaths is not None and len(a_xpaths) and '' != a_xpaths[0].strip():
            self._si_directive = a_xpaths[0].strip()

            # extract view id and overwrite super's field
            self._si_view = self._si_directive.replace(self._local_id('directive')+'-', '', 1)
        # otherwise generate uuid
        else:
            self._si_view = uuid.uuid4().hex
            self._si_directive = self._local_id('directive')+'-'+self._si_view

        self._parse_directive(extras)


    @abc.abstractmethod
    def _parse_directive(self, extras=None):
        # no-op
        return None


    def _directive_text():
        ye_directive = self._ye_directive

        # rich text body; join all text within
        if len(ye_directive.findall('./ac:rich-text-body', H_NAMESPACES)):
            return ' '.join(ye_directive.xpath('./ac:rich-text-body//text()', namespaces=H_NAMESPACES))
        # plain text body; join all text within
        else:
            return ' '.join(ye_directive.xpath('./ac:plain-text-body//text()', namespaces=H_NAMESPACES))


    def _insert(self, render, hide_directive=False) -> str:
        ye_render = render
        b_hide_directive = hide_directive

        # find directive id param
        ye_param_id = self._ye_directive.find('./ac:parameter[@ac:name="id"]', H_NAMESPACES)

        # no such param yet
        if ye_param_id is None:
            # create param
            ye_param_id = _ac_element('parameter', {'name': 'id'})

            # insert as 1st child
            self._ye_directive.insert(0, ye_param_id)

        # set param id text
        ye_param_id.text = self._si_directive

        # hide the directive
        if b_hide_directive:
            # find style parameter
            ye_param_style = self._ye_directive.find('./ac:parameter[@ac:name="style"]', H_NAMESPACES)

            # no style currently set
            if ye_param_style is None:
                # create style parameter element
                ye_param_style = _ac_element('parameter', {'name': 'style'})

                # set parameter value
                ye_param_style.text = 'display:none;'

                # append as sibling to id parameter
                ye_param_id.addnext(ye_param_style)

        # insert view render element immediately following directive element
        self._ye_directive.addnext(ye_render)

        # return modified content
        return _lxml_to_string(self._ye_root)



class PageReference(NamedTuple):
    '''
    Descriptor for a page reference
    '''
    space: str
    title: str
    page_id: str=None
    text: str=None
    iri: str=None


class Table(DirectedView):
    # local prefix def
    def _prefix(self, a_append: List[str]=[]) -> str:
        return super()._prefix(a_append+['table'])

    def _parse_directive(self, h_extras: Dict[str, Hash]={}):
        ye_directive = self._ye_directive

        # page ref
        ye_page = ye_directive.find('.//ac:link/ri:page', H_NAMESPACES)
        if ye_page is not None:
            si_ref_space = ''.join(ye_directive.xpath('.//ac:link/ri:page/@ri:space-key', namespaces=H_NAMESPACES))
            si_ref_title = ''.join(ye_directive.xpath('.//ac:link/ri:page/@ri:content-title', namespaces=H_NAMESPACES))
        # nothing
        else:
            raise Exception(f'Table view directive is not understood: """{_lxml_to_string(ye_directive)}"""')

        self._g_template_ref = PageReference(
            space=h_extras['directive_page_space']['value'],
            title=h_extras['directive_page_title']['value'],
            page_id=h_extras['directive_page_id']['value'],
            text=h_extras['directive_link_text']['value'] if 'directive_link_text' in h_extras else self._directive_text(),
            iri=h_extras['view_template_def']['value'],
        )

    @property
    def template_ref(self) -> PageReference:
        return self._g_template_ref


    def render(self, k_query_results: QueryResultsTable) -> str:
        # build Confluence table as XHTML string
        s_xhtml = k_query_results.to_confluence_xhtml(
            span_id=self._local_id('render')+'-'+self._si_view,
        )

        # create render element
        ye_render = _lxml_from_string(s_xhtml)[0]

        # return fully serialized document after insertion
        return self._insert(
            render=ye_render,
            hide_directive=True,
        )


class Tooltip(DirectedView):
    # local prefix def
    def _prefix(self, a_append: List[str]=[]) -> str:
        return super().prefix(a_append+['tooltip'])

    def render(self, s_tooltip_text: str, s_tooltip_link: str) -> str:
        # Replace contents of insertHover span with link
        if s_tooltip_link:
            ye_insertHover_body = ye_xref.find(f'./ac:rich-text-body', H_NAMESPACES)
            if ye_insertHover_body is not None:
                # Strip all tags from body leaving only text
                etree.strip_tags(ye_insertHover_body, '*')
                # Insert link into body
                ye_link = etree.Element('a', {'href':s_tooltip_link})
                ye_insertHover_body.append(ye_link)
                # Move text from body into link
                ye_link.text = ye_insertHover_body.text
                ye_insertHover_body.text = ''

        # Locate existing tooltip with same "id" parameter as insertHover span, or create one
        a_tooltip_macros = ye_root.xpath(f'.//ac:structured-macro[@ac:name="tooltip"]/ac:parameter[@ac:name="id" and text() = "{si_xref_tooltip_id}"]/..', namespaces=H_NAMESPACES)
        if len(a_tooltip_macros) == 0:
            ye_tooltip_macro = _ac_element('structured-macro', {
                'name': 'tooltip',
                'schema-version': '1',
                'macro_id': uuid.uuid4().hex
            })
            ye_tooltip_param_id = _ac_element('parameter', {'name':'id'})
            ye_tooltip_param_id.text = 'ced-hover-' + xref_macro_id
            ye_tooltip_macro.append(ye_tooltip_param_id)
            ye_root.append(ye_tooltip_macro)
        else:
            ye_tooltip_macro = a_tooltip_macros[0]
        
        # Set tooltip text
        ye_tooltip_text = ye_tooltip_macro.find('./ac:parameter[@ac:name="text"]', H_NAMESPACES)
        if ye_tooltip_text is None:
            ye_tooltip_text = _ac_element('parameter', {'name': 'text'})
            ye_tooltip_macro.append(ye_tooltip_text)
        ye_tooltip_text.text = s_tooltip_text

        # Return modified content
        return _lxml_to_string(ye_root)


class Diagram(View):
    # local prefix def
    def _prefix(self, a_append: List[str]=[]) -> str:
        return super()._prefix(a_append+['diagram'])

    def render(self) -> str:
        # create render element
        (si_macro, ye_render) = _span(
            id=self._local_id('render')+'-'+self._si_view,
            body=[
                # etree.fromstring(f'<svg ...>'+s_content+'</svg>', parser=Y_LXML_PARSER)
                _element('svg',
                    attrs={
                        # ...
                    },
                    children=[
                        # ...
                    ],
                ),
            ],
        )

        # return fully serialized document after insertion
        return self._insert(
            render=ye_render,
        )

