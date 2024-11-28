CREATE TABLE storages (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    nickname VARCHAR(63) NOT NULL UNIQUE
);

CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    model_path TEXT NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('service', 'local')),
    token VARCHAR(255),
    context_window INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE TABLE files (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    name VARCHAR(255) NOT NULL,
    local_path TEXT NOT NULL,
    type VARCHAR(50) NOT NULL CHECK (type IN ('image', 'video', 'link', 'pdf')),
    source VARCHAR(50),
    storage_id INT NOT NULL,
    FOREIGN KEY (storage_id) REFERENCES storages(id) ON DELETE CASCADE
);

CREATE TABLE chats (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    name VARCHAR(255) NOT NULL,
    model_id INT NOT NULL,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE RESTRICT
);

CREATE TABLE chat_history (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    author VARCHAR(50) NOT NULL CHECK (author IN ('model', 'user')),
    chat_id INT NOT NULL,
    text TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
