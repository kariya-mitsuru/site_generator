# -*- coding: utf-8 -*-

import json
import os
import re

import jsonschema


class Validator(object):
    _json_schema = {
        'type': 'object',
        'require': ['base_url', 'database_name', 'namespaces', 'ids'],
        'additionalProperties': False,
        'properties': {
            'base_url': {
                'type': 'string',
                'format': 'uri-reference',
            },
            'database_name': {
                'type': 'string',
            },
            'ids': {
                'type': 'array',
                'items': {
                    '$ref': '#/definitions/index_id',
                },
            },
            'namespaces': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'require': ['namespace', 'path_prefixes', 'indexes'],
                    'additionalProperties': False,
                    'properties': {
                        'namespace': {
                            'type': 'array',
                            'minItems': 1,
                            'items': {
                                'type': 'string',
                                'pattern': '[^/]+',
                            },
                        },
                        'path_prefixes': {
                            'type': 'array',
                            'minItems': 1,
                            'items': {
                                'type': 'string',
                                'pattern': '[^/]+',
                            },
                        },
                        'cpp_version': {
                            'type': 'string',
                            'enum': ['98', '03', '11', '14', '17', '20'],
                        },
                        'indexes': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'require': ['id'],
                                'additionalProperties': False,
                                'properties': {
                                    'id': {
                                        'type': 'integer',
                                    },
                                    'page_id': {
                                        'type': 'array',
                                        'minItems': 1,
                                        'items': {
                                            'type': 'string',
                                            'pattern': '[^/]+',
                                        },
                                    },
                                    'related_to': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'integer',
                                        },
                                    },
                                    'nojump': {
                                        'type': 'boolean',
                                    },
                                    'attributes': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'string',
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        'definitions': {
            'index_id': {
                'type': 'object',
                'oneOf': [
                    {'$ref': '#/definitions/header'},
                    {'$ref': '#/definitions/common'},
                ],
            },
            'header': {
                'require': ['type', 'key'],
                'additionalProperties': False,
                'properties': {
                    'type': {
                        'type': 'string',
                        'enum': ['header'],
                    },
                    'key': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'pattern': '[^"<>]+',
                        },
                    },
                    'cpp_namespace': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'pattern': '[^:]+',
                        },
                    },
                },
            },
            'common': {
                'require': ['type', 'key'],
                'additionalProperties': False,
                'properties': {
                    'type': {
                        'type': 'string',
                        'enum': ['class', 'function', 'mem_fun', 'macro', 'enum', 'variable', 'type-alias', 'article'],
                    },
                    'key': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'pattern': '[^:]+',
                        },
                    },
                    'cpp_namespace': {
                        'type': 'array',
                        'items': {
                            'type': 'string',
                            'pattern': '[^:]+',
                        },
                    },
                },
            },
        },
    }

    def validate(self, json):
        jsonschema.validate(json, self._json_schema)


class Generator(object):
    class IndexIDGenerator(object):
        def __init__(self):
            self._ids = []

        def get_indexid(self, indexid):
            for n, id in enumerate(self._ids):
                if indexid == id:
                    return n
            n = len(self._ids)
            self._ids.append(indexid)
            return n

        def get_all(self):
            return self._ids

    _CPP_LATEST_VERSION = '20'
    _CPP_LATEST = 'cpp' + _CPP_LATEST_VERSION
    _CPP_RE_RAW = r'cpp\d+[a-zA-Z]?'
    _CPP_RE = re.compile(_CPP_RE_RAW)

    _DEPRECATED_IN_CPP_RE = re.compile(r'^' + _CPP_RE_RAW + r'deprecated' + r'$')
    _REMOVED_IN_CPP_RE = re.compile(r'^' + _CPP_RE_RAW + r'removed' + r'$')

    _HASH_HEADER_RE = re.compile(r'^( *?\n)*#(?P<header>.*?)#*(\n|$)(?P<remain>(.|\n)*)', re.MULTILINE)
    _SETEXT_HEADER_RE = re.compile(r'^( *?\n)*(?P<header>.*?)\n=+[ ]*(\n|$)(?P<remain>(.|\n)*)', re.MULTILINE)
    _REMOVE_ESCAPE_RE = re.compile(r'\\(.)')
    _META_RE = re.compile(r'^\s*\*\s*(?P<target>.*?)\[meta\s+(?P<name>.*?)\]\s*$')
    _NOT_ATTRIBUTE_RE = re.compile(r'^' + _CPP_RE_RAW + r'$')

    def split_title(self, md):
        r"""先頭の見出し部分を（あるなら）取り出す

        >>> md = '''
        ... # header
        ...
        ... contents
        ... '''
        >>> Generator().split_title(md)
        ('header', '\ncontents\n')
        >>> md = '''
        ... header
        ... ======
        ...
        ... contents
        ... '''
        >>> Generator().split_title(md)
        ('header', '\ncontents\n')
        >>> md = '''
        ... contents
        ... '''
        >>> Generator().split_title(md)
        (None, '\ncontents\n')
        """
        m = self._HASH_HEADER_RE.match(md)
        if m is None:
            m = self._SETEXT_HEADER_RE.match(md)
        if m is None:
            return None, md
        return self._REMOVE_ESCAPE_RE.sub(r'\1', m.group('header').strip()), m.group('remain')

    def get_meta(self, md):
        """メタ情報を取り出す

        >>> md = '''
        ... # foo
        ...
        ... content
        ...
        ... * foo[meta text]
        ... * bar[meta text2]
        ... * piyo[meta text]
        ... '''
        {'text': ['foo', 'piyo'], 'text2': ['bar']}
        """
        result = {}
        lines = md.split('\n')
        for line in lines:
            m = self._META_RE.match(line)
            if m is not None:
                target = m.group('target')
                name = m.group('name')
                if name not in result:
                    result[name] = []
                result[name].append(target)
        return result

    def make_index(self, md, names, idgen):
        title, contents = self.split_title(md)
        metas = self.get_meta(md)

        # type 判別
        # metas['id-type']: class, class template, function, function template, enum, variable, type-alias, macro, namespace
        # type: "header" / "class" / "function" / "mem_fun" / "macro" / "enum" / "variable"/ "type-alias" / "article"
        if 'id-type' not in metas and 'header' in metas:
            type = 'header'
        elif 'id-type' not in metas and (names[0] == 'article' or names[0] == 'lang'):
            # lang/ 直下は meta 扱いにする
            if names[0] == 'lang' and len(names) == 2:
                type = 'meta'
            else:
                # それ以外の article/ と lang/ の下は article 扱いにする
                type = 'article'
        elif 'id-type' not in metas and '/'.join(names).startswith('reference/concepts'):
            # 特殊扱い
            type = 'article'
        elif 'id-type' not in metas and '/'.join(names).startswith('reference/container_concepts'):
            # 特殊扱い
            type = 'article'
        elif 'id-type' not in metas:
            raise RuntimeError(f'unexpected meta: {metas}')
        elif metas['id-type'][0] == 'class' or metas['id-type'][0] == 'class template':
            type = 'class'
        elif metas['id-type'][0] == 'function' or metas['id-type'][0] == 'function template':
            if 'class' in metas or 'class template' in metas:
                type = 'mem_fun'
            else:
                type = 'function'
        elif metas['id-type'][0] == 'enum':
            type = 'enum'
        elif metas['id-type'][0] == 'variable':
            type = 'variable'
        elif metas['id-type'][0] == 'type-alias':
            type = 'type-alias'
        elif metas['id-type'][0] == 'macro':
            type = 'macro'
        elif metas['id-type'][0] == 'namespace':
            type = 'namespace'
        else:
            raise RuntimeError(f'unexpected meta: {metas}')

        keys = []
        if 'class' in metas:
            keys = metas['class']
        elif 'class template' in metas:
            keys = metas['class template']

        # namespace 判別
        if 'namespace' in metas:
            cpp_namespaces = metas['namespace'][0].split('::')
        else:
            cpp_namespaces = None

        index_id = {
            'type': type,
            'key': keys + [title],
        }

        if cpp_namespaces is not None:
            index_id['cpp_namespace'] = cpp_namespaces

        index = {
            'id': idgen.get_indexid(index_id),
            'page_id': names[1:-1] + [names[-1][:-3]],  # remove .md
        }

        related_to = []
        if 'class' in metas:
            related_to.append(idgen.get_indexid({
                'type': 'class',
                'key': metas['class'][0].split('::'),
            }))
        if 'header' in metas:
            related_to.append(idgen.get_indexid({
                'type': 'header',
                'key': metas['header'][0].split('/'),
            }))

        if len(related_to) != 0:
            index['related_to'] = related_to

        if 'cpp' in metas:
            attributes = [cpp for cpp in metas['cpp'] if not self._NOT_ATTRIBUTE_RE.match(cpp)]
            if attributes:
                removed = any([attr for attr in attributes if self._REMOVED_IN_CPP_RE.match(attr)])

                if removed:
                    attributes.append('removed_in_latest')

                elif any([attr for attr in attributes if self._DEPRECATED_IN_CPP_RE.match(attr)]):
                    attributes.append('deprecated_in_latest')

                index['attributes'] = attributes

        return index

    def generate(self, base_dir, file_paths):
        idgen = Generator.IndexIDGenerator()

        indices = []
        for file_path in file_paths:
            if not file_path.startswith(base_dir):
                raise RuntimeError(f'{file_path} not starts with {base_dir}')
            if not file_path.endswith('.md'):
                raise RuntimeError(f'{file_path} not ends with .md')

            print(f'processing {file_path}...')
            names = list(filter(None, file_path[len(base_dir):].split('/')))
            with open(file_path) as f:
                md = f.read()
            index = self.make_index(md, names, idgen)
            # C++ のバージョン情報を入れる
            cpp_version = None
            metas = self.get_meta(md)
            if 'cpp' in metas:
                if any(map(lambda cpp: cpp == 'cpp11', metas['cpp'])):
                    cpp_version = '11'
                elif any(map(lambda cpp: cpp == 'cpp14', metas['cpp'])):
                    cpp_version = '14'
                elif any(map(lambda cpp: cpp == 'cpp17', metas['cpp'])):
                    cpp_version = '17'
                elif any(map(lambda cpp: cpp == 'cpp20', metas['cpp'])):
                    cpp_version = '20'

            indices.append((names, cpp_version, index))

        # (names[0], cpp_version) が同じものをまとめる
        namespaces = {}
        for names, cpp_version, index in indices:
            key = (names[0], cpp_version)
            if key in namespaces:
                namespaces[key]['indexes'].append(index)
            else:
                namespace = {
                    'namespace': [names[0]],
                    'path_prefixes': [names[0]],
                    'indexes': [index],
                }
                if cpp_version is not None:
                    namespace['cpp_version'] = cpp_version
                namespaces[key] = namespace

        namespaces = sorted(namespaces.values(), key=lambda ns: ns['namespace'])

        result = {
            'base_url': 'https://cpprefjp.github.io',
            'database_name': 'cpprefjp',
            'namespaces': namespaces,
            'ids': idgen.get_all(),
        }
        return result


def get_files(base_dir):
    for dirpath, dirnames, filenames in os.walk(base_dir):
        for filename in filenames:
            if filename[-3:] == ".md" and not filename[0].isupper():
                yield os.path.join(dirpath, filename)


def main():
    paths = list(get_files('site/article')) + list(get_files('site/lang')) + list(get_files('site/reference'))
    result = Generator().generate('site', paths)
    with open('crsearch.json', 'wb') as f:
        f.write(json.dumps(result, separators=(',', ':'), ensure_ascii=False, sort_keys=True).encode('utf-8'))


if __name__ == '__main__':
    main()
