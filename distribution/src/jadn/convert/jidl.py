"""
Translate JADN to JADN Interface Definition Language
"""
import json
from datetime import datetime
import re
from jadn.definitions import *
from jadn import topts_s2d, ftopts_s2d, opts_d2s, get_optx, raise_error
from jadn import jadn2typestr, typestr2jadn, jadn2fielddef, fielddef2jadn, cleanup_tagid


"""
Convert JADN to JIDL
"""


def jidl_dumps(schema, width=None):
    w = {
        'meta': 12,
        'id': 4,
        'name': 12,
        'type': 35,
        'page': None
    }
    if width:
        w.update(width)

    text = ''
    meta = schema['meta'] if 'meta' in schema else {}
    mlist = [k for k in META_ORDER if k in meta]
    for k in mlist + list(set(meta) - set(mlist)):              # Display meta elements in fixed order
        text += f'{k:>{w["meta"]}}: {json.dumps(meta[k])}\n'    # TODO: wrap to page width, continuation-line parser

    wt = w['id'] + w['name'] + w['type']
    for td in schema['types']:
        tdef = f'{td[TypeName]} = {jadn2typestr(td[BaseType], td[TypeOptions])}'
        tdesc = '// ' + td[TypeDesc] if td[TypeDesc] else ''
        text += f'\n{tdef:<{wt}}{tdesc}'[:w['page']] + '\n'
        idt = td[BaseType] == 'Array' or get_optx(td[TypeOptions], 'id') is not None
        for fd in td[Fields] if len(td) > Fields else []:       # TODO: constant-length types
            fname, fdef, fmult, fdesc = jadn2fielddef(fd, td)
            if td[BaseType] == 'Enumerated':
                fdesc = '// ' + fdesc if fdesc else ''
                fs = f'{fd[ItemID]:>{w["id"]}} {fname}'
                wf = w['id'] + w['name'] + 2
            else:
                fdef += '' if fmult == '1' else ' optional' if fmult == '0..1' else ' [' + fmult + ']'
                fdesc = '// ' + fdesc if fdesc else ''
                wn = 0 if idt else w['name']
                fs = f'{fd[FieldID]:>{w["id"]}} {fname:<{wn}} {fdef}'
                wf = w['id'] + w['type'] if idt else wt
            text += f'{fs:{wf}}{fdesc}'[:w['page']] + '\n'
    return text


def jidl_dump(schema, fname, source=''):
    with open(fname, 'w', encoding='utf8') as f:
        if source:
            f.write('/* Generated from ' + source + ', ' + datetime.ctime(datetime.now()) + ' */\n\n')
        f.write(jidl_dumps(schema))


"""
Convert JIDL to JADN
"""


def line2jadn(line, tdef):
    if line:
        p_meta = r'^\s*([-\w]+):\s*(.+?)\s*$'
        m = re.match(p_meta, line)
        if m:
            return 'M', (m.group(1), m.group(2))

        p_tname = r'\s*([-$\w]+)'               # Type Name
        p_assign = r'\s*='                      # Type assignment operator
        p_tstr  = r'\s*(.*?)\s*\{?'             # Type definition
        p_tdesc = r'(?:\s*\/\/\s*(.*?)\s*)?'    # Optional Type description
        p_type = '^' + p_tname + p_assign + p_tstr + p_tdesc + '$'
        m = re.match(p_type, line)
        if m:
            btype, topts, fo = typestr2jadn(m.group(2))
            assert fo == []                     # field options MUST not be included in typedefs
            newtype = [m.group(1), btype, topts, m.group(3) if m.group(3) else '', []]
            return 'T', newtype

        p_id = r'\s*(\d+)'                      # Field ID
        p_fname = r'\s+([-:$\w]+\/?)?'          # Field Name with dir/ option (colon is deprecated, allow for now)
        p_fstr = r'\s*(.*?),?'                  # Field definition or Enum value
        p_range = r'\s*(?:\[([.*\d]+)\]|(optional))?,?'     # Multiplicity
        p_desc = r'\s*(?:\/\/\s*(.*?)\s*)?'     # Field description, including field name if .id option
        pn = '()' if (get_optx(tdef[TypeOptions], 'id') is not None or tdef[BaseType] == 'Array') else p_fname
        if tdef[BaseType] == 'Enumerated':      # Parse Enumerated Item
            pattern = '^' + p_id + p_fstr + p_desc + '$'
            m = re.match(pattern, line)
            if m:
                return 'F', fielddef2jadn(int(m.group(1)), m.group(2), '', '', m.group(3) if m.group(3) else '')
        else:                                   # Parse Field
            pattern = '^' + p_id + pn + p_fstr + p_range + p_desc + '$'
            m = re.match(pattern, line)
            if m:
                range = '0..1' if m.group(5) else m.group(4)        # Convert 'optional' to range
                fdesc = m.group(6) if m.group(6) else ''
                return 'F', fielddef2jadn(int(m.group(1)), m.group(2), m.group(3), range if range else '', fdesc)

        if line.strip() not in ('', '}'):
            raise_error(f'JIDL load{repr(line)}')
    return '', ''


def jidl_loads(doc):
    meta = {}
    types = []
    fields = None
    for n, line in enumerate(doc.splitlines(), start=1):
        if line:
            t, v = line2jadn(line, types[-1] if types else None)    # Parse a JIDL line
            if t == 'F':
                fields.append(v)
            elif fields:
                cleanup_tagid(fields)
                fields = None
            if t == 'M':
                meta.update({v[0]: json.loads(v[1])})
            elif t == 'T':
                types.append(v)
                fields = types[-1][Fields]
    return {'meta': meta, 'types': types} if meta else {'types': types}


def jidl_load(fname):
    with open(fname, 'r') as f:
        return jidl_loads(f.read())