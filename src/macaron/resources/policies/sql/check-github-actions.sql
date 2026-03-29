-- Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
-- Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

-- Failed check facts for check-github-actions policy template.
SELECT
    analysis.analysis_time,
    gha_check.vulnerability_urls AS vulnerability,
    gha_check.github_actions_id AS third_party_action_name,
    gha_check.github_actions_version AS third_party_action_version,
    gha_check.caller_workflow AS vulnerable_workflow
FROM github_actions_vulnerabilities_check AS gha_check
JOIN check_facts
    ON check_facts.id = gha_check.id
JOIN check_result
    ON check_result.id = check_facts.check_result_id
JOIN component
    ON check_result.component_id = component.id
JOIN analysis
    ON analysis.id = component.analysis_id
WHERE check_result.passed = 0;
