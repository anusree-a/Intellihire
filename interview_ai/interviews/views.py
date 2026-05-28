from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
import uuid
from django.db.models import Avg
import openpyxl

from .models import (
    InterviewSession, CheatingEvent, Question,
    Company, HRUser, SubscriptionPlan
)
from .agent import InterviewAgent
from .resume_parser import parse_resume_for_session


# ============================================================
# HOME PAGE
# ============================================================

def home(request):
    return render(request, 'home.html')


# ============================================================
# COMPANY REGISTRATION FLOW
# ============================================================

def subscription_page(request):
    """Show subscription plans"""
    plans = SubscriptionPlan.objects.all()
    return render(request, 'subscription.html', {'plans': plans})


def company_details(request, plan_name):
    """Collect company details after plan selection"""
    plan = get_object_or_404(SubscriptionPlan, name=plan_name)
    if request.method == 'POST':
        request.session['company_data'] = {
            'name': request.POST.get('company_name'),
            'email': request.POST.get('company_email'),
            'phone': request.POST.get('company_phone', ''),
            'address': request.POST.get('company_address', ''),
            'industry': request.POST.get('company_industry', ''),
            'company_size': request.POST.get('company_size', ''),
            'website': request.POST.get('company_website', ''),
            'admin_name': request.POST.get('admin_name'),
            'admin_password': request.POST.get('admin_password'),
            'plan_name': plan.name,
        }
        return redirect('payment_page', plan_name=plan.name)

    return render(request, 'company_details.html', {'plan': plan})


def payment_page(request, plan_name):
    """Dummy payment page"""
    plan = get_object_or_404(SubscriptionPlan, name=plan_name)
    company_data = request.session.get('company_data')

    if not company_data:
        return redirect('subscription_page')

    if request.method == 'POST':
        company = Company.objects.create(
            name=company_data['name'],
            email=company_data['email'],
            phone=company_data.get('phone', ''),
            address=company_data.get('address', ''),
            industry=company_data.get('industry', ''),
            company_size=company_data.get('company_size', ''),
            website=company_data.get('website', ''),
            plan=plan,
            payment_status='paid',
            payment_id=str(uuid.uuid4())[:12].upper(),
        )
        company.set_password(company_data['admin_password'])
        company.save()

        request.session['company_id'] = company.id
        request.session['company_email'] = company.email
        request.session['company_admin'] = True

        if 'company_data' in request.session:
            del request.session['company_data']

        messages.success(request, f'Welcome! {company.name} is registered.')
        return redirect('company_dashboard')

    return render(request, 'payment.html', {'plan': plan, 'company_data': company_data})


# ============================================================
# COMPANY DASHBOARD & SESSION
# ============================================================

def company_portal(request):
    """Company intermediate portal page for login or registration"""
    return render(request, 'company_portal.html')

def company_login(request):
    """Company admin login"""
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            company = Company.objects.get(email=email, is_active=True)
            if company.check_password(password):
                request.session['company_id'] = company.id
                request.session['company_email'] = company.email
                request.session['company_admin'] = True
                messages.success(request, f'Welcome back, {company.name}!')
                return redirect('company_dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
        except Company.DoesNotExist:
            messages.error(request, 'Company not found.')

    return render(request, 'company_login.html')


def company_dashboard(request):
    """Company admin dashboard"""
    company_id = request.session.get('company_id')
    if not company_id or not request.session.get('company_admin'):
        return redirect('home')

    company = get_object_or_404(Company, id=company_id)
    hr_users = HRUser.objects.filter(company=company)
    interviews = InterviewSession.objects.filter(company=company)

    context = {
        'company': company,
        'hr_users': hr_users,
        'interviews': interviews,
        'total_interviews': interviews.count(),
        'completed_interviews': interviews.filter(status='COMPLETED').count(),
        'avg_score': interviews.filter(score__isnull=False).aggregate(avg=Avg('score'))['avg'] or 0,
    }
    return render(request, 'company_dashboard.html', context)


@require_http_methods(["POST"])
def add_hr_user(request):
    """Add a new HR user under the company"""
    company_id = request.session.get('company_id')
    if not company_id:
        return redirect('home')

    company = get_object_or_404(Company, id=company_id)

    name = request.POST.get('hr_name')
    email = request.POST.get('hr_email')
    password = request.POST.get('hr_password')

    if HRUser.objects.filter(email=email).exists():
        messages.error(request, f'An HR user with email {email} already exists.')
        return redirect('company_dashboard')

    hr = HRUser(company=company, name=name, email=email)
    hr.set_password(password)
    hr.save()

    messages.success(request, f'HR user {name} added successfully!')
    return redirect('company_dashboard')


def company_logout(request):
    """Logout company admin"""
    request.session.flush()
    return redirect('home')


# ============================================================
# HR LOGIN & DASHBOARD
# ============================================================

def hr_login(request):
    """HR user login page"""
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            hr = HRUser.objects.get(email=email, is_active=True)
            if hr.check_password(password):
                hr.last_login = timezone.now()
                hr.save()

                request.session['hr_id'] = hr.id
                request.session['hr_email'] = hr.email
                request.session['hr_company_id'] = hr.company.id
                request.session['hr_logged_in'] = True

                messages.success(request, f'Welcome, {hr.name}!')
                return redirect('hr_dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
        except HRUser.DoesNotExist:
            messages.error(request, 'HR user not found.')

    return render(request, 'hr_login.html')


def hr_dashboard(request):
    """HR dashboard"""
    if not request.session.get('hr_logged_in'):
        return redirect('hr_login')

    hr_id = request.session.get('hr_id')
    company_id = request.session.get('hr_company_id')

    hr = get_object_or_404(HRUser, id=hr_id)
    company = get_object_or_404(Company, id=company_id)
    sessions = InterviewSession.objects.filter(company=company).order_by('-score', '-created_at')

    context = {
        'hr': hr,
        'company': company,
        'sessions': sessions,
        'stats': {
            'total': sessions.count(),
            'completed': sessions.filter(status='COMPLETED').count(),
            'in_progress': sessions.filter(status='IN_PROGRESS').count(),
            'avg_score': round(
                sessions.filter(score__isnull=False).aggregate(avg=Avg('score'))['avg'] or 0, 2
            ),
        }
    }
    return render(request, 'hr_dashboard.html', context)


def hr_logout(request):
    """Logout HR"""
    request.session.flush()
    return redirect('home')


def create_interview_session(request):
    """Create interview (HR only)"""
    if not request.session.get('hr_logged_in'):
        return redirect('hr_login')

    if request.method == 'POST':
        company_id = request.session.get('hr_company_id')
        hr_id = request.session.get('hr_id')

        session = InterviewSession.objects.create(
            candidate_name=request.POST.get('candidate_name'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone', ''),
            company_id=company_id,
            created_by_id=hr_id,
        )

        send_interview_invitation_email(session)
        messages.success(request, f'Interview created for {session.candidate_name}.')
        return redirect('hr_dashboard')

    return render(request, 'create_interview.html')


@require_http_methods(["POST"])
def cancel_interview(request, token):
    """HR cancels interview"""
    if not request.session.get('hr_logged_in'):
        return redirect('hr_login')

    session = get_object_or_404(InterviewSession, token=token)
    if session.status in ['COMPLETED', 'TERMINATED', 'CANCELLED']:
        messages.warning(request, 'Cannot cancel this interview.')
        return redirect('interview_detail', token=token)

    reason = request.POST.get('reason', 'Cancelled by HR')
    session.cancel_interview(cancelled_by=request.session.get('hr_email', 'HR'), reason=reason)
    send_cancellation_email(session)
    messages.success(request, f'Interview cancelled for {session.candidate_name}.')
    return redirect('hr_dashboard')


def interview_detail(request, token):
    """HR views interview detail"""
    session = get_object_or_404(InterviewSession, token=token)
    questions = Question.objects.filter(session=session)
    cheating_events = CheatingEvent.objects.filter(session=session)
    return render(request, 'interview_detail.html', {
        'session': session,
        'questions': questions,
        'cheating_events': cheating_events,
    })

# ============================================================
# EDIT INTERVIEW SCORE (HR ONLY)
# ============================================================

def edit_interview_score(request, token):
    if not request.session.get('hr_logged_in'):
        return redirect('hr_login')

    session = get_object_or_404(InterviewSession, token=token)

    if request.method == "POST":
        session.score = request.POST.get("score")
        session.technical_score = request.POST.get("technical_score")
        session.communication_score = request.POST.get("communication_score")
        session.evaluation_report = request.POST.get("evaluation_report")
        session.save()

        messages.success(request, "Score updated successfully")
        return redirect('hr_dashboard')

    return render(request, 'edit_interview.html', {'session': session})

# ============================================================
# CANDIDATE-FACING INTERVIEW VIEWS
# ============================================================

def interview_page(request, token):
    """Main interview interface with access control"""
    session = get_object_or_404(InterviewSession, token=token)
    session.record_access()

    if not session.can_access_interview():
        if session.status == 'COMPLETED':
            return render(request, 'interview_completed.html', {'session': session})
        elif session.status == 'TERMINATED':
            return render(request, 'interview_terminated.html', {'session': session})
        elif session.status == 'CANCELLED':
            return render(request, 'interview_cancelled.html', {'session': session})

    require_resume = settings.INTERVIEW_CONFIG.get('REQUIRE_RESUME_UPLOAD', True)
    if require_resume and not session.resume:
        return render(request, 'interview_upload_resume.html', {'session': session})

    return render(request, 'interview.html', {'session': session})


# ============================================================
# API ENDPOINTS
# ============================================================

@api_view(['POST'])
def upload_resume_api(request, token):
    """API endpoint for candidate to upload resume before interview"""
    session = get_object_or_404(InterviewSession, token=token)

    if not session.can_access_interview():
        return Response({'error': 'Interview no longer accessible'}, status=status.HTTP_403_FORBIDDEN)

    if session.status != 'CREATED':
        return Response({'error': 'Resume can only be uploaded before interview starts'}, status=status.HTTP_400_BAD_REQUEST)

    resume_file = request.FILES.get('resume')
    if not resume_file:
        return Response({'error': 'No resume file provided'}, status=status.HTTP_400_BAD_REQUEST)

    ext = resume_file.name.lower()[resume_file.name.rfind('.'):]
    if ext not in ['.pdf', '.docx']:
        return Response({'error': 'Only PDF and DOCX files are allowed'}, status=status.HTTP_400_BAD_REQUEST)

    if resume_file.size > 5 * 1024 * 1024:
        return Response({'error': 'File size must be less than 5MB'}, status=status.HTTP_400_BAD_REQUEST)

    session.resume = resume_file
    session.save()

    try:
        parse_resume_for_session(session)
    except Exception as e:
        print(f"Resume parsing error: {e}")

    return Response({'success': True, 'message': 'Resume uploaded successfully'})


@api_view(['POST'])
def start_interview_api(request, token):
    """API endpoint to start the interview"""
    session = get_object_or_404(InterviewSession, token=token)

    if not session.can_access_interview():
        return Response({
            'error': 'This interview is no longer accessible',
            'status': session.status
        }, status=status.HTTP_403_FORBIDDEN)

    require_resume = settings.INTERVIEW_CONFIG.get('REQUIRE_RESUME_UPLOAD', True)
    if require_resume and not session.resume:
        return Response({'error': 'Please upload your resume first'}, status=status.HTTP_400_BAD_REQUEST)

    session.camera_permission = request.data.get('camera_permission', False)
    session.microphone_permission = request.data.get('microphone_permission', False)
    session.save()

    if session.resume and not session.parsed_resume_data:
        try:
            parse_resume_for_session(session)
        except Exception as e:
            print(f"Resume parsing error during start: {e}")

    agent = InterviewAgent(session)
    response = agent.start_interview()

    return Response({
        'success': True,
        'message': response.get('message'),
        'stage': response.get('stage'),
        'session_status': session.status
    })


@api_view(['POST'])
def send_message_api(request, token):
    """API endpoint to send candidate message to AI agent"""
    session = get_object_or_404(InterviewSession, token=token)

    if session.status != 'IN_PROGRESS':
        return Response({'error': 'Interview is not active', 'session_status': session.status}, status=status.HTTP_400_BAD_REQUEST)

    candidate_message = request.data.get('message', '').strip()
    if not candidate_message:
        return Response({'error': 'Message cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)

    agent = InterviewAgent(session)
    response = agent.process_message(candidate_message)

    # Question saving is handled inside agent._update_agent_state
    # Do NOT save here again — would cause duplicates

    if response.get('action') == 'conclude':
        send_interview_report_email(session)
        return Response({
            'success': True,
            'message': response.get('message'),
            'stage': response.get('stage'),
            'action': 'conclude',
            'session_status': session.status
        })

    return Response({
        'success': True,
        'message': response.get('message'),
        'stage': response.get('stage'),
        'action': response.get('action'),
        'session_status': session.status
    })


@api_view(['POST'])
def log_cheating_event_api(request, token):
    """API endpoint to log anti-cheating events"""
    session = get_object_or_404(InterviewSession, token=token)

    event_type = request.data.get('event_type')
    if not event_type:
        return Response({'error': 'event_type is required'}, status=status.HTTP_400_BAD_REQUEST)

    CheatingEvent.objects.create(
        session=session,
        event_type=event_type,
        metadata=request.data.get('metadata', {})
    )

    session.cheating_score += 1
    session.cheating_events.append({
        'type': event_type,
        'timestamp': timezone.now().isoformat(),
        'metadata': request.data.get('metadata', {})
    })
    session.save()

    threshold = settings.INTERVIEW_CONFIG.get('ANTI_CHEAT_THRESHOLD', 5)
    if session.cheating_score >= threshold:
         agent = InterviewAgent(session)
         agent.generate_final_evaluation()
         session.terminate_interview()
         return Response({'success': True, 'warning': 'Too many violations detected', 'terminated': True})

    return Response({'success': True, 'cheating_score': session.cheating_score})


@api_view(['POST'])
def transcribe_audio_api(request, token):
    """API endpoint for speech-to-text (frontend handles transcription)"""
    session = get_object_or_404(InterviewSession, token=token)

    transcription = request.data.get('transcription', '')
    if not transcription:
        return Response({'error': 'No transcription provided'}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'success': True, 'transcription': transcription})

@api_view(['POST'])
def upload_video_api(request, token):
    session = get_object_or_404(InterviewSession, token=token)

    video_file = request.FILES.get("video")

    if not video_file:
        return Response({"error": "No video uploaded"}, status=400)

    session.video_recording = video_file
    session.save()

    return Response({"success": True, "message": "Video saved"})


@api_view(['GET'])
def interview_status_api(request, token):
    """Get current interview status"""
    session = get_object_or_404(InterviewSession, token=token)
    return Response({
        'status': session.status,
        'stage': session.current_stage,
        'cheating_score': session.cheating_score,
        'questions_asked': session.agent_state.get('questions_asked', 0),
        'conversation_history': session.conversation_history[-10:],
        'resume_uploaded': bool(session.resume),
        'can_access': session.can_access_interview()
    })


# ============================================================
# BULK UPLOAD
# ============================================================

def bulk_upload_excel(request):
    """HR bulk creates interview sessions from Excel file"""
    if not request.session.get('hr_logged_in'):
        return redirect('hr_login')

    if request.method == 'GET':
        return render(request, 'bulk_upload.html')

    # POST
    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        messages.error(request, "No file uploaded.")
        return render(request, 'bulk_upload.html')

    try:
        workbook = openpyxl.load_workbook(excel_file)
        sheet = workbook.active

        company_id = request.session.get('hr_company_id')
        hr_id = request.session.get('hr_id')

        for row in sheet.iter_rows(min_row=2, values_only=True):
            name, email, phone = row

            if not name or not email:
                continue

            session = InterviewSession.objects.create(
                candidate_name=name,
                email=email,
                phone=str(phone) if phone else '',
                company_id=company_id,
                created_by_id=hr_id,
            )

            send_interview_invitation_email(session)

        messages.success(request, "Bulk interviews created successfully!")

    except Exception as e:
        print("Excel Error:", e)
        messages.error(request, "Error processing Excel file.")

    return redirect('hr_dashboard')


# ============================================================
# EMAIL UTILITIES
# ============================================================

def send_interview_invitation_email(session):
    """Send interview link to candidate"""
    url = f"http://localhost:8000/interview/{session.token}/"
    send_mail(
        "Interview Invitation",
        f"Hi {session.candidate_name},\n\nYou've been invited to an AI-powered interview.\n\nLink: {url}\n\n"
        f"Instructions:\n- Upload your resume (PDF or DOCX)\n- Allow camera and microphone\n- Find a quiet place\n- Link can only be used ONCE\n\nGood luck!",
        settings.DEFAULT_FROM_EMAIL,
        [session.email],
        fail_silently=False,
    )


def send_interview_report_email(session):
    """Send interview report to HR"""
    send_mail(
        f"Interview Report - {session.candidate_name}",
        f"Interview completed for: {session.candidate_name}\nEmail: {session.email}\nStatus: {session.status}\n\n"
        f"Overall Score: {session.score}/10\nTechnical Score: {session.technical_score}/10\n"
        f"Communication Score: {session.communication_score}/10\nViolations: {session.cheating_score}\n\n"
        f"View: http://localhost:8000/hr/interview/{session.token}/\n\n{session.evaluation_report}",
        settings.DEFAULT_FROM_EMAIL,
        [settings.HR_EMAIL],
        fail_silently=True,
    )


def send_cancellation_email(session):
    """Send cancellation notification to candidate"""
    send_mail(
        "Interview Cancelled",
        f"Hi {session.candidate_name},\n\nYour interview was cancelled.\nReason: {session.cancellation_reason or 'Administrative decision'}\n\n"
        f"If this is an error, please contact our HR department.",
        settings.DEFAULT_FROM_EMAIL,
        [session.email],
        fail_silently=True,
    )

   