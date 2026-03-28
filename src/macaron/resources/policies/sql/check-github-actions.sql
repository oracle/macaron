-- Copyright (c) 2026 - 2026, Oracle and/or its affiliates. All rights reserved.
-- Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

-- Failed check facts for check-github-actions policy template.
SELECT
    c.id AS component_id,
    c.purl AS component_purl,
    gha.*
FROM github_actions_vulnerabilities_check AS gha
JOIN check_facts AS cf
    ON cf.id = gha.id
JOIN check_result AS cr
    ON cr.id = cf.check_result_id
JOIN component AS c
    ON cr.component_id = c.id
WHERE cr.passed = 0;
