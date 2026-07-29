"""Create approval service tables.

Revision ID: 001
Revises: 
Create Date: 2024-01-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types first
    approval_action = sa.Enum(
        'publish', 'price_change', 'discount', 'confirm_reservation',
        'validate_invoice', 'rectify_invoice', 'cancel_invoice',
        'present_taxes', 'make_payment', 'modify_chart_accounts',
        'modify_tax_rates', 'modify_fiscal_data', 'launch_paid_campaign',
        'update_production', 'delete_data', 'bulk_export',
        name='approval_action', create_type=True
    )
    
    approval_priority = sa.Enum(
        'low', 'medium', 'high', 'critical',
        name='approval_priority', create_type=True
    )
    
    approval_status = sa.Enum(
        'pending', 'approved', 'rejected', 'expired', 
        'cancelled', 'executing', 'completed', 'failed',
        name='approval_status', create_type=True
    )

    # Create approval_requests table
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('action', sa.Enum('publish', 'price_change', 'discount', 'confirm_reservation',
                                    'validate_invoice', 'rectify_invoice', 'cancel_invoice',
                                    'present_taxes', 'make_payment', 'modify_chart_accounts',
                                    'modify_tax_rates', 'modify_fiscal_data', 'launch_paid_campaign',
                                    'update_production', 'delete_data', 'bulk_export',
                                    name='approval_action', create_type=False), nullable=False),
        sa.Column('action_type', sa.String(100), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('current_state', sa.JSONB, nullable=False, server_default='{}'),
        sa.Column('proposed_state', sa.JSONB, nullable=False, server_default='{}'),
        sa.Column('risk_level', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('risk_factors', sa.JSONB, nullable=False, server_default='[]'),
        sa.Column('evidence_urls', sa.JSONB, nullable=False, server_default='[]'),
        sa.Column('evidence_notes', sa.Text(), nullable=True),
        sa.Column('requested_by', sa.String(100), nullable=False, index=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('auto_approve_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_reject_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending', index=True),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approval_comment', sa.Text(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('execution_result', sa.JSONB, nullable=True),
        sa.Column('execution_error', sa.Text(), nullable=True),
        sa.Column('task_id', sa.String(100), nullable=True, index=True),
        sa.Column('idempotency_key', sa.String(100), unique=True, nullable=True, index=True),
        sa.Column('metadata', sa.JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate='CURRENT_TIMESTAMP', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate='CURRENT_TIMESTAMP', nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_approval_requests_status', 'approval_requests', ['status'])
    op.create_index('ix_approval_requests_requested_by', 'approval_requests', ['requested_by'])
    op.create_index('ix_approval_requests_expires_at', 'approval_requests', ['expires_at'])
    op.create_index('ix_approval_requests_idempotency_key', 'approval_requests', ['idempotency_key'], unique=True)
    
    # Create approval_comments table
    op.create_table(
        'approval_comments',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('approval_id', sa.Uuid(as_uuid=True), sa.ForeignKey('approval_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_id', sa.String(100), nullable=False),
        sa.Column('author_name', sa.String(200), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_approval_comments_approval_id', 'approval_comments', ['approval_id'])
    
    # Create approval_history table
    op.create_table(
        'approval_history',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('approval_id', sa.Uuid(as_uuid=True), sa.ForeignKey('approval_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_status', sa.String(50), nullable=False),
        sa.Column('to_status', sa.String(50), nullable=False),
        sa.Column('changed_by', sa.String(100), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_approval_history_approval_id', 'approval_history', ['approval_id'])
    op.create_index('ix_approval_history_created', 'approval_history', ['created_at'])
    
    # Create approval_rules table
    op.create_table(
        'approval_rules',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('action', sa.String(50), nullable=False, unique=True, index=True),
        sa.Column('required', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('min_approvers', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('allowed_roles', sa.JSONB(), nullable=False, server_default='[]'),
        sa.Column('auto_approve_if', sa.JSONB(), nullable=True),
        sa.Column('auto_reject_if', sa.JSONB(), nullable=True),
        sa.Column('max_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('min_approvals', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('require_comment', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('expiry_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('auto_approve_hours', sa.Integer(), nullable=True),
        sa.Column('auto_reject_hours', sa.Integer(), nullable=True),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('escalation_hours', sa.Integer(), nullable=True),
        sa.Column('escalation_to', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Insert default rules
    op.execute("""
        INSERT INTO approval_rules (action, required, min_approvers, allowed_roles, priority, expiry_hours, auto_reject_hours)
        VALUES
            ('publish', true, 1, '["supervisor", "admin"]', 'high', 8, 24),
            ('price_change', true, 1, '["supervisor", "admin"]', 'high', 8, 24),
            ('discount', true, 1, '["supervisor", "admin"]', 'high', 8, 24),
            ('confirm_reservation', true, 1, '["supervisor", "admin"]', 'high', 8, 24),
            ('validate_invoice', true, 1, '["accounting", "admin"]', 'high', 8, 24),
            ('rectify_invoice', true, 1, '["accounting", "admin"]', 'high', 8, 24),
            ('cancel_invoice', true, 1, '["accounting", "admin"]', 'critical', 2, 24),
            ('present_taxes', true, 1, '["accounting", "admin"]', 'critical', 2, 24),
            ('make_payment', true, 1, '["accounting", "admin"]', 'high', 8, 24),
            ('modify_chart_accounts', true, 1, '["accounting", "admin"]', 'critical', 2, 24),
            ('modify_tax_rates', true, 1, '["accounting", "admin"]', 'critical', 2, 24),
            ('modify_fiscal_data', true, 1, '["accounting", "admin"]', 'critical', 2, 24),
            ('launch_paid_campaign', true, 1, '["marketing", "admin"]', 'medium', 24, 48),
            ('update_production', true, 1, '["tech_lead", "admin"]', 'critical', 2, 24),
            ('delete_data', true, 2, '["admin"]', 'critical', 1, 24),
            ('bulk_export', true, 1, '["admin", "dpo"]', 'medium', 24, 48)
    """)
    
    # Create approval_rules_history for audit trail of rule changes
    op.create_table(
        'approval_rules_history',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('rule_id', sa.Uuid(as_uuid=True), sa.ForeignKey('approval_rules.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('changed_fields', sa.JSONB(), nullable=False, server_default='{}'),
        sa.Column('changed_by', sa.String(100), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_approval_rules_history_rule_id', 'approval_rules_history', ['rule_id'])


def downgrade() -> None:
    op.drop_table('approval_rules_history')
    op.drop_table('approval_rules')
    op.drop_index('ix_approval_history_created', table_name='approval_history')
    op.drop_index('ix_approval_history_approval_id', table_name='approval_history')
    op.drop_table('approval_history')
    op.drop_index('ix_approval_comments_approval_id', table_name='approval_comments')
    op.drop_table('approval_comments')
    op.drop_index('ix_approval_requests_idempotency_key', table_name='approval_requests')
    op.drop_index('ix_approval_requests_expires_at', table_name='approval_requests')
    op.drop_index('ix_approval_requests_requested_by', table_name='approval_requests')
    op.drop_index('ix_approval_requests_status', table_name='approval_requests')
    op.drop_table('approval_requests')
    op.execute('DROP TYPE IF EXISTS approval_status')
    op.execute('DROP TYPE IF EXISTS approval_priority')
    op.execute('DROP TYPE IF EXISTS approval_action')