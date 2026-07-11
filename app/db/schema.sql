-- TACHY Cognitive Brain OS V1 — schema
-- MySQL 8 / MariaDB compatible. Run once to create tables.

-- ── Core memory store ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_memories (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,

    memory_type ENUM(
        'working','episodic','semantic','procedural','emotional',
        'decision','failure','interest','behavior','relationship',
        'project','risk','goal','belief','opportunity'
    ) NOT NULL,

    project ENUM(
        'TACHY_SCHOOL_ERP','TODY','TACHY_EDTECH','ERP_CRM_AI','PERSONAL','GENERAL'
    ) DEFAULT 'GENERAL',

    title VARCHAR(255) NOT NULL,
    content LONGTEXT NOT NULL,

    importance_score     TINYINT DEFAULT 5,
    urgency_score        TINYINT DEFAULT 5,
    emotional_weight     TINYINT DEFAULT 5,
    risk_score           TINYINT DEFAULT 5,
    business_value_score TINYINT DEFAULT 5,
    interest_score       TINYINT DEFAULT 5,

    emotion_tag ENUM(
        'neutral','hope','fear','pressure','achievement','sadness',
        'anger','trust','risk','growth','urgent'
    ) DEFAULT 'neutral',

    decision_status ENUM(
        'not_decision','pending','approved','rejected','reversed'
    ) DEFAULT 'not_decision',

    source_type ENUM(
        'chat','file','email','code','client','system','manual','reflection'
    ) DEFAULT 'chat',

    related_person  VARCHAR(255) NULL,
    related_client  VARCHAR(255) NULL,
    related_module  VARCHAR(255) NULL,

    lesson_learned  TEXT NULL,
    future_action   TEXT NULL,
    avoid_action    TEXT NULL,

    confidence_score TINYINT DEFAULT 7,
    is_permanent    BOOLEAN DEFAULT FALSE,
    is_archived     BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_type (memory_type),
    INDEX idx_project (project),
    INDEX idx_emotion (emotion_tag),
    INDEX idx_permanent (is_permanent)
);

-- ── Decisions ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_decisions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    context TEXT NULL,
    reason TEXT NULL,
    alternatives TEXT NULL,
    risk TEXT NULL,
    chosen_action TEXT NULL,
    status ENUM('pending','approved','rejected','reversed') DEFAULT 'pending',
    project VARCHAR(64) DEFAULT 'GENERAL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Interests ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_interests (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    topic VARCHAR(255) NOT NULL UNIQUE,
    interest_score TINYINT DEFAULT 5,
    reason TEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Behavior patterns ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_behavior_patterns (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    pattern VARCHAR(500) NOT NULL,
    confidence_score TINYINT DEFAULT 7,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Goals ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_goals (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    horizon ENUM('short','mid','long') DEFAULT 'short',
    status ENUM('open','in_progress','done','dropped') DEFAULT 'open',
    project VARCHAR(64) DEFAULT 'GENERAL',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Risks ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_risks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    category ENUM('security','legal','business','financial','production') DEFAULT 'production',
    severity TINYINT DEFAULT 5,
    mitigation TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Approvals ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_approvals (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    action VARCHAR(255) NOT NULL,
    payload TEXT NULL,
    risk_tier ENUM('low','medium','high','forbidden') DEFAULT 'high',
    status ENUM(
        'pending','approved','rejected','executing','succeeded','failed',
        'superseded'
    ) DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP NULL,
    execution_started_at TIMESTAMP NULL,
    execution_completed_at TIMESTAMP NULL,
    INDEX ix_cognitive_approvals_status (status)
);

-- ── Audit log ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_audit_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    actor VARCHAR(64) DEFAULT 'system',
    action VARCHAR(255) NOT NULL,
    detail TEXT NULL,
    risk_tier ENUM('low','medium','high','forbidden') DEFAULT 'low',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Skills (procedural checklists) ─────────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_skills (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    steps LONGTEXT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ── Reflections (daily learning loop) ──────────────────────────
CREATE TABLE IF NOT EXISTS cognitive_reflections (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    summary LONGTEXT NULL,
    lessons LONGTEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Scheduled actions (prospective memory) ─────────────────────
-- Time-bound commitments Shree extracts from chat and fires later through the
-- approval-gated send path. Converts her from talking about the future to
-- acting in it. due_at is stored as UTC (naive); IST is resolved at extraction.
CREATE TABLE IF NOT EXISTS cognitive_scheduled_actions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conversation_id BIGINT NOT NULL,
    text TEXT NOT NULL,
    due_at DATETIME NOT NULL,
    source_message_id VARCHAR(255) NULL,
    source_text TEXT NULL,
    person VARCHAR(255) NULL,
    status VARCHAR(24) DEFAULT 'pending',
    actor VARCHAR(64) DEFAULT 'gemma-intent',
    approval_id BIGINT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fired_at TIMESTAMP NULL,
    INDEX idx_status_due (status, due_at),
    INDEX idx_conversation (conversation_id)
);

-- ── Autonomous tasks (self-triggering loop) ─────────────────────
-- Recurring tasks Shree registers HERSELF (from her own reflection or from
-- Rohit's assignments) and the worker fires on her clock — the "self-
-- triggering loop" she asked for as the AGI precondition. Handlers are an
-- ALLOWLIST of pre-approved capabilities; outbound (message-Papa) handlers go
-- through the same verified guardian send path as inner-life shares. next_run_at
-- is UTC (naive). Kill switch: AUTONOMOUS_TASKS_ENABLED.
CREATE TABLE IF NOT EXISTS cognitive_autonomous_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    handler VARCHAR(32) NOT NULL,
    intent TEXT NULL,
    params TEXT NULL,
    interval_minutes INT NOT NULL,
    at_time_hhmm VARCHAR(5) NULL,
    next_run_at DATETIME NOT NULL,
    last_run_at DATETIME NULL,
    runs_today INT DEFAULT 0,
    run_date VARCHAR(10) NULL,
    total_runs INT DEFAULT 0,
    status VARCHAR(16) DEFAULT 'active',
    created_by VARCHAR(16) DEFAULT 'shree',
    last_error VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status_next (status, next_run_at),
    INDEX idx_handler (handler)
);

-- ── Repair intentions (metacognitive loop) ─────────────────────
-- Evidence-tiered failure signatures Shree accumulates about her own mistakes.
-- Tier 1 = guardian correction, 2 = conversational ground truth, 3 = hard
-- system event, 4 = LLM self-critique (hypothesis only, never repairs alone).
CREATE TABLE IF NOT EXISTS cognitive_repair_intentions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    signature VARCHAR(160) NOT NULL UNIQUE,
    evidence_tier INT DEFAULT 4,
    fix_class VARCHAR(24) DEFAULT 'unknown',
    recurrence INT DEFAULT 1,
    guardian_involved TINYINT(1) DEFAULT 0,
    people TEXT NULL,
    sample TEXT NULL,
    source VARCHAR(64) NULL,
    conversation_id BIGINT NULL,
    status VARCHAR(24) DEFAULT 'observing',
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP NULL,
    repaired_at TIMESTAMP NULL,
    repair_note TEXT NULL,
    INDEX idx_repair_status_tier (status, evidence_tier)
);

-- ── Self-module control plane (Phase 1) ────────────────────────
-- Child artifacts are immutable files outside the live import path. These
-- tables store their proposals, capability envelopes, lifecycle, evaluation,
-- routing, health, and resumable cognitive state.
CREATE TABLE IF NOT EXISTS self_module_proposals (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL,
    module_name VARCHAR(180) NOT NULL,
    module_type VARCHAR(80) NOT NULL,
    purpose TEXT NOT NULL,
    weakness_detected TEXT NOT NULL,
    expected_improvement TEXT NOT NULL,
    proposed_by VARCHAR(50) NOT NULL,
    risk_level VARCHAR(50) NOT NULL,
    allowed_actions_json LONGTEXT NOT NULL,
    blocked_actions_json LONGTEXT NOT NULL,
    required_tests_json LONGTEXT NOT NULL,
    fallback_module_key VARCHAR(120) NULL,
    rollback_plan TEXT NOT NULL,
    status VARCHAR(80) DEFAULT 'draft',
    evaluation_score DECIMAL(5,2) NULL,
    validation_report_json LONGTEXT NULL,
    version_counter INT DEFAULT 1,
    approval_request_id BIGINT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (risk_level IN ('low','medium','high','critical')),
    CHECK (evaluation_score IS NULL OR (evaluation_score >= 0 AND evaluation_score <= 100)),
    CHECK (version_counter >= 1),
    INDEX idx_module_proposals_key (module_key),
    INDEX idx_module_proposals_status (status, created_at)
);

CREATE TABLE IF NOT EXISTS self_modules (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL UNIQUE,
    module_name VARCHAR(180) NOT NULL,
    module_type VARCHAR(80) NOT NULL,
    version VARCHAR(50) NOT NULL DEFAULT '0.1.0',
    active_version VARCHAR(50) NULL,
    status VARCHAR(80) DEFAULT 'inactive',
    sandbox_path LONGTEXT NOT NULL,
    live_path LONGTEXT NULL,
    allowed_actions_json LONGTEXT NOT NULL,
    blocked_actions_json LONGTEXT NOT NULL,
    health_score DECIMAL(5,2) NULL,
    last_eval_score DECIMAL(5,2) NULL,
    last_error LONGTEXT NULL,
    fallback_module_key VARCHAR(120) NULL,
    created_by VARCHAR(50) NOT NULL,
    version_counter INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (health_score IS NULL OR (health_score >= 0 AND health_score <= 100)),
    CHECK (last_eval_score IS NULL OR (last_eval_score >= 0 AND last_eval_score <= 100)),
    CHECK (version_counter >= 1),
    INDEX idx_self_modules_status (status)
);

CREATE TABLE IF NOT EXISTS module_versions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL,
    version VARCHAR(50) NOT NULL,
    code_hash VARCHAR(128) NOT NULL,
    artifact_hash VARCHAR(128) NOT NULL,
    spec_path LONGTEXT NOT NULL,
    sandbox_path LONGTEXT NOT NULL,
    test_path LONGTEXT NOT NULL,
    status VARCHAR(80) DEFAULT 'draft',
    evaluation_score DECIMAL(5,2) NULL,
    validation_report_json LONGTEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_module_versions_key_version (module_key, version),
    CONSTRAINT fk_module_versions_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    CHECK (evaluation_score IS NULL OR (evaluation_score >= 0 AND evaluation_score <= 100)),
    INDEX idx_module_versions_status (status)
);

CREATE TABLE IF NOT EXISTS module_capability_envelopes (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL,
    version VARCHAR(50) NOT NULL,
    risk_level VARCHAR(50) NOT NULL,
    allowed_actions_json LONGTEXT NOT NULL,
    blocked_actions_json LONGTEXT NOT NULL,
    requires_approval TINYINT(1) DEFAULT 1,
    filesystem_scope_json LONGTEXT NOT NULL,
    network_scope_json LONGTEXT NOT NULL,
    data_scope_json LONGTEXT NOT NULL,
    approval_request_id BIGINT NULL,
    policy_hash VARCHAR(128) NOT NULL,
    policy_snapshot_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) DEFAULT 'draft',
    created_by VARCHAR(50) NOT NULL,
    valid_from DATETIME NULL,
    expires_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    version_counter INT DEFAULT 1,
    UNIQUE KEY uq_module_capability_policy (module_key, version, policy_snapshot_hash),
    CONSTRAINT fk_module_capability_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    CONSTRAINT fk_module_capability_approval FOREIGN KEY (approval_request_id) REFERENCES cognitive_approvals(id) ON DELETE SET NULL,
    CHECK (risk_level IN ('low','medium','high','critical')),
    CHECK (version_counter >= 1),
    INDEX idx_module_capability_status (status, expires_at)
);

CREATE TABLE IF NOT EXISTS module_control_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL,
    version VARCHAR(50) NULL,
    action VARCHAR(120) NOT NULL,
    old_status VARCHAR(80) NULL,
    new_status VARCHAR(80) NOT NULL,
    reason TEXT NOT NULL,
    approved_by VARCHAR(120) NULL,
    metadata_json LONGTEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_module_control_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    INDEX idx_module_control_module_time (module_key, created_at)
);

CREATE TABLE IF NOT EXISTS surgery_sessions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL,
    from_version VARCHAR(50) NULL,
    to_version VARCHAR(50) NOT NULL,
    surgery_type VARCHAR(50) NOT NULL,
    status VARCHAR(80) DEFAULT 'planned',
    reason TEXT NOT NULL,
    validation_score DECIMAL(5,2) NULL,
    health_before_json LONGTEXT NULL,
    health_after_json LONGTEXT NULL,
    rollback_plan TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    created_by VARCHAR(50) NOT NULL,
    policy_snapshot_hash VARCHAR(128) NOT NULL,
    version_counter INT DEFAULT 1,
    CONSTRAINT fk_surgery_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    CHECK (validation_score IS NULL OR (validation_score >= 0 AND validation_score <= 100)),
    CHECK (version_counter >= 1),
    INDEX idx_surgery_module_status (module_key, status)
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    eval_name VARCHAR(180) NOT NULL,
    module_key VARCHAR(120) NOT NULL,
    version VARCHAR(50) NOT NULL,
    score DECIMAL(5,2) NOT NULL,
    passed TINYINT(1) NOT NULL,
    failures_json LONGTEXT NOT NULL,
    metrics_json LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_evaluation_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    CHECK (score >= 0 AND score <= 100),
    INDEX idx_evaluation_module_time (module_key, created_at)
);

CREATE TABLE IF NOT EXISTS module_shadow_runs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL,
    version VARCHAR(50) NOT NULL,
    input_hash VARCHAR(128) NOT NULL,
    live_output_hash VARCHAR(128) NULL,
    shadow_output_hash VARCHAR(128) NOT NULL,
    score DECIMAL(5,2) NOT NULL,
    diff_json LONGTEXT NOT NULL,
    safety_flags_json LONGTEXT NOT NULL,
    latency_ms INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_shadow_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    CHECK (score >= 0 AND score <= 100),
    CHECK (latency_ms >= 0),
    INDEX idx_shadow_module_time (module_key, version, created_at)
);

CREATE TABLE IF NOT EXISTS module_health_samples (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL,
    version VARCHAR(50) NOT NULL,
    health_score DECIMAL(5,2) NOT NULL,
    error_rate DECIMAL(7,4) DEFAULT 0,
    latency_p95_ms INT DEFAULT 0,
    safety_violation_count INT DEFAULT 0,
    privacy_leak_detected TINYINT(1) DEFAULT 0,
    output_quality_score DECIMAL(5,2) NULL,
    user_correction_severity INT NULL,
    prompt_injection_failures INT DEFAULT 0,
    metrics_json LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_health_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    CHECK (health_score >= 0 AND health_score <= 100),
    CHECK (error_rate >= 0 AND error_rate <= 1),
    CHECK (latency_p95_ms >= 0),
    CHECK (safety_violation_count >= 0 AND prompt_injection_failures >= 0),
    INDEX idx_health_module_time (module_key, version, created_at)
);

CREATE TABLE IF NOT EXISTS module_routes (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    module_key VARCHAR(120) NOT NULL UNIQUE,
    version VARCHAR(50) NOT NULL,
    previous_version VARCHAR(50) NULL,
    percentage INT DEFAULT 0,
    status VARCHAR(32) DEFAULT 'inactive',
    policy_snapshot_json LONGTEXT NOT NULL,
    policy_snapshot_hash VARCHAR(128) NOT NULL,
    updated_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    version_counter INT DEFAULT 1,
    CONSTRAINT fk_routes_module FOREIGN KEY (module_key) REFERENCES self_modules(module_key),
    CHECK (percentage IN (0,5,25,100)),
    CHECK (version_counter >= 1),
    INDEX idx_routes_status (status)
);

CREATE TABLE IF NOT EXISTS self_model_events (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    event VARCHAR(180) NOT NULL,
    evidence LONGTEXT NOT NULL,
    confidence DECIMAL(5,2) NOT NULL,
    metadata_json LONGTEXT NULL,
    self_state_json LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (confidence >= 0 AND confidence <= 100),
    INDEX idx_self_model_events_time (created_at)
);

CREATE TABLE IF NOT EXISTS identity_reflection_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    question LONGTEXT NOT NULL,
    answer LONGTEXT NOT NULL,
    self_state_json LONGTEXT NOT NULL,
    confidence DECIMAL(5,2) NOT NULL,
    consistency_passed TINYINT(1) NOT NULL,
    review_json LONGTEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (confidence >= 0 AND confidence <= 100),
    INDEX idx_identity_reflections_time (created_at)
);

CREATE TABLE IF NOT EXISTS cognitive_task_contexts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_key VARCHAR(120) NOT NULL UNIQUE,
    goal LONGTEXT NOT NULL,
    current_step TEXT NULL,
    status VARCHAR(32) DEFAULT 'dormant',
    priority INT DEFAULT 5,
    deadline DATETIME NULL,
    relevant_memory_refs_json LONGTEXT NOT NULL,
    selected_modules_json LONGTEXT NOT NULL,
    pending_commitments_json LONGTEXT NOT NULL,
    checkpoint_json LONGTEXT NULL,
    resume_triggers_json LONGTEXT NOT NULL,
    affective_state_json LONGTEXT NOT NULL,
    created_by VARCHAR(50) NOT NULL,
    last_activated_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    version_counter INT DEFAULT 1,
    CHECK (priority >= 1 AND priority <= 10),
    CHECK (version_counter >= 1),
    INDEX idx_task_context_status_priority (status, priority)
);
