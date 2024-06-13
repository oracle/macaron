import pprint
import sys

from macaron.code_analyzer.dataflow_analysis.github_workflow_extractor import extract_from_workflow
from macaron.parsers.actionparser import parse

workflow_filepath = sys.argv[1]

workflow = parse(workflow_filepath)

node = extract_from_workflow(workflow)

pprint.pprint(node, width=200)
