from django.db import models
import uuid
from django.utils import timezone
from django.contrib.auth.hashers import make_password


class SubscriptionPlan(models.Model):
    PLAN_CHOICES = [
        ('basic', 'Basic'),
        ('professional', 'Professional'),
        ('premium', 'Premium'),
    ]

    name = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    interviews_per_month = models.IntegerField()
    ai_features = models.BooleanField(default=False)
    analytics = models.BooleanField(default=False)
    priority_support = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - ${self.price}/mo"


class Company(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    industry = models.CharField(max_length=100, blank=True)
    company_size = models.CharField(max_length=50, blank=True)
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)
    website = models.URLField(blank=True)

    # Subscription
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    subscription_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    # Payment
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_id = models.CharField(max_length=100, blank=True)

    # Admin credentials
    admin_password = models.CharField(max_length=256)  # hashed
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def set_password(self, raw_password):
        self.admin_password = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.admin_password)


class HRUser(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='hr_users')
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=256)  # hashed
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.email})"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password)


# ============== INTERVIEW MODELS ==============

class InterviewSession(models.Model):
    STATUS_CHOICES = [
        ('CREATED', 'Created'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('TERMINATED', 'Terminated'),
        ('CANCELLED', 'Cancelled'),
    ]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    candidate_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, null=True)
    resume = models.FileField(upload_to="resumes/", null=True, blank=True)
    video_recording = models.FileField(upload_to="interview_videos/", null=True, blank=True)

    # Linked to company & hr
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(HRUser, on_delete=models.SET_NULL, null=True, blank=True)

    # Interview State
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="CREATED")
    current_stage = models.CharField(max_length=50, default="greeting")

    # Link usage tracking
    link_accessed = models.BooleanField(default=False)
    link_access_count = models.IntegerField(default=0)
    first_access_at = models.DateTimeField(null=True, blank=True)
    last_access_at = models.DateTimeField(null=True, blank=True)

    # AI Agent Memory
    conversation_history = models.JSONField(default=list, blank=True)
    agent_state = models.JSONField(default=dict, blank=True)

    # Resume Analysis
    parsed_resume_data = models.JSONField(default=dict, blank=True)

    # Responses & Transcript
    transcript = models.TextField(blank=True)
    responses = models.JSONField(default=list, blank=True)

    # Anti-cheating
    cheating_events = models.JSONField(default=list, blank=True)
    cheating_score = models.IntegerField(default=0)

    # Evaluation
    score = models.FloatField(null=True, blank=True)
    technical_score = models.FloatField(null=True, blank=True)
    communication_score = models.FloatField(null=True, blank=True)
    evaluation_report = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.CharField(max_length=100, blank=True)
    cancellation_reason = models.TextField(blank=True)

    # Permissions
    camera_permission = models.BooleanField(default=False)
    microphone_permission = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.candidate_name} - {self.status}"

    def can_access_interview(self):
        """Check if candidate can access the interview"""
        if self.status in ['COMPLETED', 'TERMINATED', 'CANCELLED']:
            return False
        return True

    def record_access(self):
        """Record that the link was accessed"""
        now = timezone.now()
        self.link_access_count += 1
        self.last_access_at = now
        if not self.link_accessed:
            self.link_accessed = True
            self.first_access_at = now
        self.save()

    def start_interview(self):
        """Start the interview"""
        self.status = 'IN_PROGRESS'
        self.started_at = timezone.now()
        self.save()

    def complete_interview(self):
        """Complete the interview"""
        self.status = 'COMPLETED'
        self.completed_at = timezone.now()
        self.save()

    def terminate_interview(self):
        """Terminate interview due to cheating violations"""
        # Do NOT override if already completed
        if self.status == 'COMPLETED':
            return
        self.status = 'TERMINATED'
        self.completed_at = timezone.now()
        self.save()

    def cancel_interview(self, cancelled_by, reason=""):
        """Cancel the interview (by HR)"""
        self.status = 'CANCELLED'
        self.cancelled_at = timezone.now()
        self.cancelled_by = cancelled_by
        self.cancellation_reason = reason
        self.save()

    def get_greeting(self):
        """Returns correct greeting for the candidate"""
        return f"Welcome {self.candidate_name} to your interview!"


class CheatingEvent(models.Model):
    EVENT_TYPES = [
        ('TAB_SWITCH', 'Tab Switch'),
        ('WINDOW_BLUR', 'Window Lost Focus'),
        ('VISIBILITY_HIDDEN', 'Page Hidden'),
        ('CAMERA_OFF', 'Camera Turned Off'),
        ('MIC_OFF', 'Microphone Turned Off'),
        ('FULLSCREEN_EXIT', 'Exited Fullscreen'),
        ('COPY_PASTE', 'Copy/Paste Detected'),
        ('MULTIPLE_FACES', 'Multiple Faces Detected'),
        ('NO_FACE', 'No Face Detected'),
    ]

    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='cheating_logs')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.session.candidate_name} - {self.event_type} at {self.timestamp}"


class Question(models.Model):
    CATEGORY_CHOICES = [
        ('PERSONAL', 'Personal'),
        ('RESUME', 'Resume-based'),
        ('TECHNICAL', 'Technical'),
        ('CODING', 'Coding Logic'),
        ('BEHAVIORAL', 'Behavioral'),
    ]

    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    asked_at = models.DateTimeField(auto_now_add=True)

    # Response
    answer_text = models.TextField(blank=True)
    answer_received_at = models.DateTimeField(null=True, blank=True)

    # Evaluation
    score = models.FloatField(null=True, blank=True)
    feedback = models.TextField(blank=True)

    # Vague answer tracking
    was_vague = models.BooleanField(default=False)
    follow_up_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['asked_at']

    def __str__(self):
        return f"Q: {self.question_text[:50]}..."