from django.contrib import admin
from django.utils.html import format_html
from .models import InterviewSession, CheatingEvent, Question, Company, HRUser, SubscriptionPlan


@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = [
        'candidate_name', 
        'email',
        'company',
        'created_by',
        'status_badge', 
        'current_stage', 
        'score_display',
        'cheating_score',
        'created_at',
        'interview_link'
    ]
    list_filter = ['status', 'current_stage', 'company', 'created_at']
    search_fields = ['candidate_name', 'email']
    readonly_fields = [
        'token', 
        'created_at', 
        'started_at', 
        'completed_at',
        'conversation_history',
        'agent_state',
        'parsed_resume_data'
    ]
    
    fieldsets = (
        ('Candidate Information', {
            'fields': ('candidate_name', 'email', 'phone', 'resume')
        }),
        ('Interview Status', {
            'fields': ('status', 'current_stage', 'token', 'company', 'created_by')
        }),
        ('Permissions', {
            'fields': ('camera_permission', 'microphone_permission')
        }),
        ('Scores', {
            'fields': ('score', 'technical_score', 'communication_score')
        }),
        ('Data', {
            'fields': ('parsed_resume_data', 'agent_state', 'conversation_history', 'responses'),
            'classes': ('collapse',)
        }),
        ('Anti-Cheating', {
            'fields': ('cheating_score', 'cheating_events'),
            'classes': ('collapse',)
        }),
        ('Evaluation', {
            'fields': ('evaluation_report', 'transcript'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at')
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'CREATED': '#3498db',
            'IN_PROGRESS': '#f39c12',
            'COMPLETED': '#2ecc71',
            'TERMINATED': '#e74c3c',
            'CANCELLED': '#95a5a6'
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 5px 10px; border-radius: 5px;">{}</span>',
            colors.get(obj.status, '#95a5a6'),
            obj.status
        )
    status_badge.short_description = 'Status'
    
    def score_display(self, obj):
        if obj.score:
            color = '#2ecc71' if obj.score >= 7 else '#f39c12' if obj.score >= 5 else '#e74c3c'
            return format_html(
                '<strong style="color: {};">{:.1f}/10</strong>',
                color,
                obj.score
            )
        return '-'
    score_display.short_description = 'Score'
    
    def interview_link(self, obj):
        url = f'/interview/{obj.token}/'
        return format_html('<a href="{}" target="_blank">Open Interview</a>', url)
    interview_link.short_description = 'Link'


@admin.register(CheatingEvent)
class CheatingEventAdmin(admin.ModelAdmin):
    list_display = ['session', 'event_type', 'timestamp']
    list_filter = ['event_type', 'timestamp']
    search_fields = ['session__candidate_name', 'session__email']
    readonly_fields = ['timestamp']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('session')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = [
        'session',
        'short_question',
        'category',
        'score',
        'asked_at'
    ]
    list_filter = ['category', 'asked_at']
    search_fields = ['session__candidate_name', 'question_text', 'answer_text']
    readonly_fields = ['asked_at', 'answer_received_at']
    
    def short_question(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    short_question.short_description = 'Question'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('session')


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'interviews_per_month', 'ai_features', 'analytics', 'priority_support']
    list_filter = ['ai_features', 'analytics', 'priority_support']


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'plan', 'subscription_active', 'payment_status', 'created_at']
    list_filter = ['plan', 'subscription_active', 'payment_status']
    search_fields = ['name', 'email']
    readonly_fields = ['created_at', 'subscribed_at', 'payment_id']


@admin.register(HRUser)
class HRUserAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'company', 'is_active', 'last_login']
    list_filter = ['is_active', 'company']
    search_fields = ['name', 'email']
    readonly_fields = ['created_at', 'last_login']