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
    status ENUM('pending','approved','rejected') DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP NULL
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
