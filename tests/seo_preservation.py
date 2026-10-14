"""Keep approved metadata additions separate from project content preservation."""
import ast
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def assert_project_renderer_preserved(case, baseline):
    old = ast.parse(subprocess.check_output(['git', 'show', baseline + ':business/real_projects.py'], cwd=ROOT))
    new = ast.parse((ROOT / 'business/real_projects.py').read_text())
    schema = next(n for n in new.body if getattr(n, 'name', None) == 'schema_graph')
    for node in ast.walk(schema):
        if isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == 'logo' for k in node.keys):
            pairs = [(k, v) for k, v in zip(node.keys, node.values) if not (isinstance(k, ast.Constant) and k.value == 'logo')]
            node.keys, node.values = map(list, zip(*pairs))
    render = next(n for n in new.body if getattr(n, 'name', None) == 'render_project')
    # Exactly the reviewed metadata override; all project text, dates and photos remain protected.
    case.assertIsInstance(render.body[-3], ast.Assign)
    case.assertEqual(ast.unparse(render.body[-3]), 'title, description = (project.seo_title, project.meta_description)')
    case.assertIsInstance(render.body[-2], ast.If)
    case.assertEqual(ast.unparse(render.body[-2].test), "project.status == 'published' and project.slug == 'ensuite-renovation-merrow-guildford'")
    case.assertEqual({ast.unparse(n.targets[0]) for n in render.body[-2].body}, {'title', 'description'})
    render.body = render.body[:-3] + [render.body[-1]]
    render.body[-1].value.args[:2] = [ast.parse('project.seo_title', mode='eval').body, ast.parse('project.meta_description', mode='eval').body]
    case.assertEqual(ast.dump(new), ast.dump(old))
