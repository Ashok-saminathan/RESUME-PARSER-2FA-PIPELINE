-- Requires PostgreSQL 13+ (gen_random_uuid is built in).

CREATE TABLE users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name         VARCHAR(120) NOT NULL,
    email             VARCHAR(254) NOT NULL,
    phone             VARCHAR(20),
    password_hash     VARCHAR(255) NOT NULL,
    qualification     VARCHAR(200),
    skills            JSONB NOT NULL DEFAULT '[]'::jsonb,
    experience        JSONB NOT NULL DEFAULT '[]'::jsonb,
    role              VARCHAR(20) NOT NULL DEFAULT 'student',
    is_active         BOOLEAN NOT NULL DEFAULT FALSE,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TABLE user_resumes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(id) ON DELETE CASCADE,
    filename     VARCHAR(255) NOT NULL,
    content_type VARCHAR(100),
    file_size    INTEGER NOT NULL,
    file_sha256  CHAR(64) NOT NULL,
    parsed_data  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_user_resumes_user_id ON user_resumes (user_id);

CREATE TABLE otp_challenges (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel      VARCHAR(20) NOT NULL CHECK (channel IN ('email', 'whatsapp', 'browser')),
    code_hash    CHAR(64),
    totp_secret  VARCHAR(64),
    attempts     SMALLINT NOT NULL DEFAULT 0,
    max_attempts SMALLINT NOT NULL DEFAULT 5,
    expires_at   TIMESTAMPTZ NOT NULL,
    consumed_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_otp_secret_shape CHECK (
        (channel = 'browser' AND totp_secret IS NOT NULL AND code_hash IS NULL)
        OR (channel <> 'browser' AND code_hash IS NOT NULL)
    )
);
CREATE INDEX ix_otp_challenges_user_id ON otp_challenges (user_id);
