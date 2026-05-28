"""
AI Interview Agent — Fixed Version
- Separate scoring call (never loses scores even if next-question call fails)
- Candidate can say "move to next round" anytime to skip to next stage
- 10 questions per stage: personal, resume, technical
- Short greeting, no duplicate "introduce yourself"
- Proper Technical/Communication score separation
"""

import json
import re
import traceback
import requests
from django.conf import settings
from django.utils import timezone
from .models import InterviewSession, Question


# ── Question banks ────────────────────────────────────────────────────────────

PERSONAL_QUESTIONS = [
    # "introduce yourself" is asked in greeting — NOT listed here
    "What are your key strengths?",
    "What is your biggest weakness and how are you working on it?",
    "Where do you see yourself in 5 years?",
    "What are your hobbies and interests outside of work?",
    "Why did you choose this field or career?",
    "How do you handle stress and pressure?",
    "Describe a situation where you showed leadership.",
    "What motivates you to do your best work?",
    "Why are you interested in this opportunity?",
    "How do you handle conflicts or disagreements in a team?",
]

RESUME_QUESTIONS = [
    "Can you walk me through your educational background?",
    "Tell me about your most significant project and your role in it.",
    "What technologies or tools have you worked with most?",
    "Describe any internship or work experience you have had.",
    "What was the biggest challenge in one of your projects and how did you solve it?",
    "Which subject or course did you enjoy the most and why?",
    "Do you have any certifications or online courses relevant to this role?",
    "Tell me about a time you worked in a team — what was your contribution?",
    "What is the most complex technical problem you have solved so far?",
    "Is there anything on your resume you would like to highlight?",
]

TECHNICAL_QUESTIONS = [
    "What programming languages are you most comfortable with?",
    "Can you explain the difference between object-oriented and functional programming?",
    "How would you approach debugging a complex issue in production?",
    "What is your understanding of data structures like arrays, linked lists, and trees?",
    "Can you explain what REST APIs are and how they work?",
    "How do you ensure the quality and reliability of your code?",
    "What is the difference between SQL and NoSQL databases?",
    "Can you explain version control and how you use Git?",
    "How would you design a simple web application from scratch?",
    "What software development best practices do you follow?",
]

STAGE_ORDER = ['personal', 'resume', 'technical']
QUESTIONS_PER_STAGE = 10

# Keywords that mean "skip to next stage"
SKIP_KEYWORDS = [
    'move to next', 'next round', 'next stage', 'skip', 'move on',
    'go to resume', 'go to technical', 'resume round', 'technical round',
    'move to resume', 'move to technical', 'next section', 'proceed',
]


class InterviewAgent:

    def __init__(self, session: InterviewSession):
        self.session = session
        self.use_groq = settings.USE_GROQ

        if self.use_groq:
            self.api_key = settings.GROQ_API_KEY
            self.api_url = "https://api.groq.com/openai/v1/chat/completions"
            self.model = "llama-3.3-70b-versatile"
        else:
            self.api_url = "http://localhost:11434/api/chat"
            self.model = "llama3.2"

        if not self.session.agent_state:
            self.session.agent_state = self._default_state()
            self.session.save()

    def _default_state(self):
        return {
            'current_stage': 'greeting',
            'stage_question_count': {'personal': 0, 'resume': 0, 'technical': 0},
            'questions_asked_texts': [
                # Pre-mark greeting question as asked to prevent repeats
                "Can you introduce yourself briefly?",
                "Can you introduce yourself?",
                "introduce yourself",
            ],
            'performance_level': 'medium',
            'elaboration_requests': 0,
            'pending_question_text': '',
            'pending_question_category': 'PERSONAL',
            'has_pending_question': False,
        }

    # -------------------------------------------------------------------------
    # MAIN ENTRY POINT
    # -------------------------------------------------------------------------

    def process_message(self, candidate_message: str):
        is_greeting = candidate_message.startswith('__GREETING__')
        state = self.session.agent_state

        # Check if candidate wants to skip to next stage
        if not is_greeting and self._is_skip_request(candidate_message):
            return self._handle_skip_request(candidate_message)

        has_pending = (
            not is_greeting
            and state.get('has_pending_question', False)
            and state.get('pending_question_text', '').strip()
        )

        # Add candidate message to history
        if not is_greeting:
            self.session.conversation_history.append({
                'role': 'user',
                'content': candidate_message,
                'timestamp': timezone.now().isoformat()
            })

        if len(self.session.conversation_history) > 30:
            self.session.conversation_history = self.session.conversation_history[-30:]

        # SCORE the previous answer (separate dedicated call)
        score_result = None
        if has_pending:
            score_result = self._score_answer(
                question=state['pending_question_text'],
                answer=candidate_message,
            )

        # Get next question from AI
        messages = self._build_conversation_context()
        try:
            if self.use_groq:
                response_data = self._call_groq_question(messages)
            else:
                response_data = self._call_ollama_question(messages)
        except Exception as e:
            print(f"[InterviewAgent] Question call failed: {e}")
            traceback.print_exc()
            response_data = self._get_fallback_response()

        # Save Q&A using the separately fetched score
        if has_pending and score_result:
            self._save_question_answer(
                question_text=state['pending_question_text'],
                category=state.get('pending_question_category', 'PERSONAL'),
                answer_text=candidate_message,
                score=score_result.get('score'),
                feedback=score_result.get('feedback', ''),
            )

        # Add AI response to history
        self.session.conversation_history.append({
            'role': 'assistant',
            'content': response_data.get('message', ''),
            'timestamp': timezone.now().isoformat()
        })

        self._update_agent_state(response_data)
        self.session.save()
        return response_data

    # -------------------------------------------------------------------------
    # SKIP REQUEST HANDLING
    # -------------------------------------------------------------------------

    def _is_skip_request(self, message: str) -> bool:
        msg_lower = message.lower().strip()
        return any(kw in msg_lower for kw in SKIP_KEYWORDS)

    def _handle_skip_request(self, candidate_message: str):
        """Move to next stage immediately when candidate requests it."""
        state = self.session.agent_state
        current_stage = state.get('current_stage', 'personal')

        # Score pending answer before skipping
        if state.get('has_pending_question') and state.get('pending_question_text'):
            score_result = self._score_answer(
                question=state['pending_question_text'],
                answer=candidate_message,
            )
            self._save_question_answer(
                question_text=state['pending_question_text'],
                category=state.get('pending_question_category', 'PERSONAL'),
                answer_text="[Candidate requested to move to next stage]",
                score=score_result.get('score', 5) if score_result else 5,
                feedback="Candidate skipped to next stage",
            )

        # Determine next stage
        try:
            idx = STAGE_ORDER.index(current_stage)
            next_stage = STAGE_ORDER[idx + 1]
        except (ValueError, IndexError):
            self.generate_final_evaluation()
            self.session.complete_interview()
            return {
                'message': f"Thank you {self.session.candidate_name}! The interview is now complete. Our team will review your responses and get back to you soon.",
                'stage': 'close',
                'action': 'conclude',
                'question_category': 'PERSONAL',
                'evaluation': {'score': 0, 'feedback': '', 'needs_elaboration': False, 'is_vague': False}
            }

        # Advance stage
        state['current_stage'] = next_stage
        state['elaboration_requests'] = 0
        state['has_pending_question'] = False
        self.session.current_stage = next_stage

        first_question = self._get_next_question_for_stage(next_stage)
        cat_map = {'personal': 'PERSONAL', 'resume': 'RESUME', 'technical': 'TECHNICAL'}
        cat = cat_map.get(next_stage, 'PERSONAL')
        stage_labels = {'personal': 'Personal', 'resume': 'Resume', 'technical': 'Technical'}
        transition_msg = f"Sure! Moving to the {stage_labels.get(next_stage, next_stage)} stage now. {first_question}"

        state['has_pending_question'] = True
        state['pending_question_text'] = first_question
        state['pending_question_category'] = cat

        asked = state.get('questions_asked_texts', [])
        asked.append(first_question)
        state['questions_asked_texts'] = asked[-40:]

        counts = state.get('stage_question_count', {'personal': 0, 'resume': 0, 'technical': 0})
        counts[next_stage] = counts.get(next_stage, 0) + 1
        state['stage_question_count'] = counts

        self.session.agent_state = state
        self.session.conversation_history.append({
            'role': 'user',
            'content': candidate_message,
            'timestamp': timezone.now().isoformat()
        })
        self.session.conversation_history.append({
            'role': 'assistant',
            'content': transition_msg,
            'timestamp': timezone.now().isoformat()
        })
        self.session.save()

        return {
            'message': transition_msg,
            'stage': next_stage,
            'action': 'ask_question',
            'question_category': cat,
            'evaluation': {'score': 0, 'feedback': '', 'needs_elaboration': False, 'is_vague': False}
        }

    def _get_next_question_for_stage(self, stage: str) -> str:
        bank_map = {
            'personal': PERSONAL_QUESTIONS,
            'resume': RESUME_QUESTIONS,
            'technical': TECHNICAL_QUESTIONS,
        }
        bank = bank_map.get(stage, RESUME_QUESTIONS)
        asked = set(self.session.agent_state.get('questions_asked_texts', []))
        for q in bank:
            if q not in asked:
                return q
        return f"Tell me about your experience relevant to the {stage} stage."

    # -------------------------------------------------------------------------
    # SEPARATE SCORING CALL
    # -------------------------------------------------------------------------

    def _score_answer(self, question: str, answer: str) -> dict:
        """
        Dedicated lightweight call just to score the answer.
        Completely separate from next-question call so scoring never gets lost.
        """
        prompt = (
            f"Score this interview answer 1-10.\n\n"
            f"Question: {question}\nAnswer: {answer}\n\n"
            f'Reply ONLY with JSON: {{"score": 7, "feedback": "One specific sentence about this answer."}}'
        )

        try:
            if self.use_groq:
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                }
                payload = {
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.2,
                    'max_tokens': 80,
                }
                for attempt in range(2):
                    try:
                        resp = requests.post(self.api_url, headers=headers, json=payload, timeout=15)
                        resp.raise_for_status()
                        content = resp.json()['choices'][0]['message']['content'].strip()
                        parsed = self._extract_json(content)
                        if parsed and 'score' in parsed:
                            score = max(1, min(10, int(float(parsed['score']))))
                            return {'score': score, 'feedback': parsed.get('feedback', '')}
                        break
                    except requests.exceptions.Timeout:
                        if attempt == 0:
                            continue
                        break
            else:
                payload = {
                    'model': self.model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'stream': False,
                    'options': {'temperature': 0.2, 'num_predict': 80},
                }
                resp = requests.post(self.api_url, json=payload, timeout=20)
                resp.raise_for_status()
                content = resp.json()['message']['content'].strip()
                parsed = self._extract_json(content)
                if parsed and 'score' in parsed:
                    score = max(1, min(10, int(float(parsed['score']))))
                    return {'score': score, 'feedback': parsed.get('feedback', '')}

        except Exception as e:
            print(f"[InterviewAgent] Scoring call failed: {e}")

        # Heuristic fallback based on answer length
        return self._estimate_score(answer)

    def _estimate_score(self, answer: str) -> dict:
        words = len(answer.split())
        if words < 5:
            return {'score': 3, 'feedback': 'Answer was very brief. More detail needed.'}
        elif words < 15:
            return {'score': 5, 'feedback': 'Adequate but could be more detailed.'}
        elif words < 40:
            return {'score': 7, 'feedback': 'Good answer with reasonable detail.'}
        else:
            return {'score': 8, 'feedback': 'Detailed and well-explained answer.'}

    # -------------------------------------------------------------------------
    # NEXT QUESTION SYSTEM PROMPT
    # -------------------------------------------------------------------------

    def _get_question_system_prompt(self):
        state = self.session.agent_state
        stage = state.get('current_stage', 'personal')
        counts = state.get('stage_question_count', {})
        asked_texts = state.get('questions_asked_texts', [])
        q_in_stage = counts.get(stage, 0)
        remaining = QUESTIONS_PER_STAGE - q_in_stage

        try:
            idx = STAGE_ORDER.index(stage)
            next_stage = STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else 'close'
        except ValueError:
            next_stage = 'close'

        cat_map = {'personal': 'PERSONAL', 'resume': 'RESUME', 'technical': 'TECHNICAL'}
        current_cat = cat_map.get(stage, 'PERSONAL')
        asked_list = "\n".join(f"- {q}" for q in asked_texts[-20:]) if asked_texts else "None"

        resume_context = ""
        if self.session.parsed_resume_data:
            skills = self.session.parsed_resume_data.get('skills', [])[:6]
            if skills:
                resume_context = f"Candidate skills: {', '.join(skills)}\n"

        advance_rule = ""
        if q_in_stage >= QUESTIONS_PER_STAGE:
            if next_stage == 'close':
                advance_rule = f'All 30 questions done. Set action to "conclude" and write a warm closing message.\n'
            else:
                advance_rule = f'{QUESTIONS_PER_STAGE} questions done in {stage}. Set "stage" to "{next_stage}" and ask first {next_stage} question.\n'

        return f"""You are an HR interviewer. Ask the next interview question.

Candidate: {self.session.candidate_name}
Stage: {stage} ({q_in_stage}/{QUESTIONS_PER_STAGE} done, {remaining} remaining)
{resume_context}{advance_rule}
Stage question types:
- personal: strengths, weaknesses, goals, hobbies, motivation, stress, leadership
- resume: education, projects, experience, tools, certifications, teamwork
- technical: programming, debugging, data structures, APIs, databases, design

DO NOT repeat these already-asked questions:
{asked_list}

Reply with ONLY this JSON (no other text):
{{
  "message": "Your single interview question here",
  "stage": "{stage}",
  "action": "ask_question",
  "question_category": "{current_cat}"
}}"""

    # -------------------------------------------------------------------------
    # SAVE Q&A
    # -------------------------------------------------------------------------

    def _save_question_answer(self, question_text, category, answer_text, score, feedback):
        try:
            final_score = None
            if score is not None:
                try:
                    final_score = float(score)
                    final_score = max(1.0, min(10.0, final_score))
                except (ValueError, TypeError):
                    final_score = 5.0

            Question.objects.create(
                session=self.session,
                question_text=question_text,
                category=category,
                answer_text=answer_text,
                answer_received_at=timezone.now(),
                score=final_score,
                feedback=feedback,
                was_vague=False,
                follow_up_count=0,
            )
            print(f"[Agent] Saved — Q: '{question_text[:50]}' | Score: {final_score} | Cat: {category}")
        except Exception as e:
            print(f"[Agent] ERROR saving Q&A: {e}")
            traceback.print_exc()

    # -------------------------------------------------------------------------
    # UPDATE STATE
    # -------------------------------------------------------------------------

    def _update_agent_state(self, response_data):
        state = self.session.agent_state
        action = response_data.get('action', 'ask_question')
        new_stage = response_data.get('stage')

        if new_stage and new_stage not in ('close', None):
            state['current_stage'] = new_stage
            self.session.current_stage = new_stage

        if action == 'ask_question':
            new_q = response_data.get('message', '').strip()
            new_cat = response_data.get('question_category', 'PERSONAL')
            current_stage = state.get('current_stage', 'personal')

            state['elaboration_requests'] = 0
            counts = state.get('stage_question_count', {'personal': 0, 'resume': 0, 'technical': 0})
            counts[current_stage] = counts.get(current_stage, 0) + 1
            state['stage_question_count'] = counts

            asked = state.get('questions_asked_texts', [])
            asked.append(new_q)
            state['questions_asked_texts'] = asked[-40:]

            state['has_pending_question'] = True
            state['pending_question_text'] = new_q
            state['pending_question_category'] = new_cat

        elif action == 'conclude':
            state['has_pending_question'] = False
            state['pending_question_text'] = ''
            self.generate_final_evaluation()
            self.session.complete_interview()

        self.session.agent_state = state

    # -------------------------------------------------------------------------
    # FALLBACK QUESTION (when AI call fails)
    # -------------------------------------------------------------------------

    def _get_fallback_response(self):
        state = self.session.agent_state
        stage = state.get('current_stage', 'personal')
        asked = set(state.get('questions_asked_texts', []))
        counts = state.get('stage_question_count', {})
        q_in_stage = counts.get(stage, 0)

        bank_map = {
            'personal': PERSONAL_QUESTIONS,
            'resume': RESUME_QUESTIONS,
            'technical': TECHNICAL_QUESTIONS,
        }
        cat_map = {'personal': 'PERSONAL', 'resume': 'RESUME', 'technical': 'TECHNICAL'}

        # Advance stage if quota met
        if q_in_stage >= QUESTIONS_PER_STAGE:
            try:
                idx = STAGE_ORDER.index(stage)
                next_stage = STAGE_ORDER[idx + 1]
                stage = next_stage
                state['current_stage'] = next_stage
                self.session.current_stage = next_stage
            except (ValueError, IndexError):
                self.generate_final_evaluation()
                self.session.complete_interview()
                return {
                    'message': f"Thank you {self.session.candidate_name}! The interview is complete. We will be in touch soon.",
                    'stage': 'close',
                    'action': 'conclude',
                    'question_category': 'PERSONAL',
                    'evaluation': {'score': 0, 'feedback': '', 'needs_elaboration': False, 'is_vague': False}
                }

        bank = bank_map.get(stage, PERSONAL_QUESTIONS)
        cat = cat_map.get(stage, 'PERSONAL')
        question = next((q for q in bank if q not in asked), f"Tell me more about your {stage} experience.")

        return {
            'message': question,
            'stage': stage,
            'action': 'ask_question',
            'question_category': cat,
            'evaluation': {'score': 5, 'feedback': '', 'needs_elaboration': False, 'is_vague': False}
        }

    # -------------------------------------------------------------------------
    # BUILD CONVERSATION CONTEXT
    # -------------------------------------------------------------------------

    def _build_conversation_context(self):
        messages = []
        for msg in self.session.conversation_history[-14:]:
            role = msg.get('role')
            content = msg.get('content', '')
            if role in ('user', 'assistant') and content:
                messages.append({'role': role, 'content': content})
        return messages

    # -------------------------------------------------------------------------
    # API CALLS
    # -------------------------------------------------------------------------

    def _call_groq_question(self, messages):
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self._get_question_system_prompt()},
                *messages,
            ],
            'temperature': 0.4,
            'max_tokens': 200,
        }
        for attempt in range(2):
            try:
                resp = requests.post(self.api_url, headers=headers, json=payload, timeout=25)
                resp.raise_for_status()
                content = resp.json()['choices'][0]['message']['content']
                parsed = self._extract_json(content)
                if parsed and 'message' in parsed:
                    return parsed
                return self._get_fallback_response()
            except requests.exceptions.Timeout:
                if attempt == 0:
                    print("[Agent] Groq timeout, retrying...")
                    continue
                return self._get_fallback_response()
            except Exception as e:
                print(f"[Agent] Groq error: {e}")
                return self._get_fallback_response()

    def _call_ollama_question(self, messages):
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self._get_question_system_prompt()},
                *messages,
            ],
            'stream': False,
            'options': {'temperature': 0.4, 'num_predict': 200},
        }
        resp = requests.post(self.api_url, json=payload, timeout=25)
        resp.raise_for_status()
        content = resp.json()['message']['content']
        parsed = self._extract_json(content)
        if parsed and 'message' in parsed:
            return parsed
        return self._get_fallback_response()

    def _extract_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r'\{[\s\S]*?\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}

    # -------------------------------------------------------------------------
    # START INTERVIEW
    # -------------------------------------------------------------------------

    def start_interview(self):
        self.session.start_interview()
        self.session.agent_state = self._default_state()

        self.session.conversation_history = [{
            'role': 'user',
            'content': (
                f"Start the interview for {self.session.candidate_name}. "
                "Greet them by name warmly. "
                "Say in ONE short sentence the 3 stages are Personal, Resume, and Technical. "
                "No explanation of each stage. Then ask: Can you introduce yourself?"
            ),
            'timestamp': timezone.now().isoformat()
        }]
        self.session.save()
        return self.process_message('__GREETING__')

    # -------------------------------------------------------------------------
    # FINAL EVALUATION
    # -------------------------------------------------------------------------

    def generate_final_evaluation(self):
        questions = Question.objects.filter(session=self.session)
        scored_qs = [q for q in questions if q.score is not None]
        avg_score = round(sum(q.score for q in scored_qs) / len(scored_qs), 2) if scored_qs else 0.0

        qa_summary = ""
        for i, q in enumerate(questions[:20], 1):
            score_str = f"{q.score:.1f}/10" if q.score else "unscored"
            qa_summary += (
                f"Q{i} [{q.category}]: {q.question_text[:100]}\n"
                f"Answer: {q.answer_text[:150]}\nScore: {score_str}\n\n"
            )

        prompt = f"""Write a professional interview evaluation report for {self.session.candidate_name}.

Data: {questions.count()} questions, {len(scored_qs)} scored, average {avg_score}/10, {self.session.cheating_score} violations.

Q&A:
{qa_summary}

Required sections:
1. Overall Summary (2-3 sentences based on actual answers)
2. Technical Rating: X/10
3. Communication Rating: X/10
4. Top 3 Strengths (specific to this candidate)
5. Top 3 Areas for Improvement
6. Hiring Recommendation: Yes / Maybe / No — one sentence reason"""

        try:
            if self.use_groq:
                headers = {'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'}
                payload = {
                    'model': self.model,
                    'messages': [
                        {'role': 'system', 'content': 'You are a professional HR evaluator. Be specific and concise.'},
                        {'role': 'user', 'content': prompt},
                    ],
                    'temperature': 0.3,
                    'max_tokens': 700,
                }
                resp = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                evaluation_text = resp.json()['choices'][0]['message']['content']
            else:
                payload = {
                    'model': self.model,
                    'messages': [
                        {'role': 'system', 'content': 'You are a professional HR evaluator.'},
                        {'role': 'user', 'content': prompt},
                    ],
                    'stream': False,
                    'options': {'num_predict': 700},
                }
                resp = requests.post(self.api_url, json=payload, timeout=35)
                resp.raise_for_status()
                evaluation_text = resp.json()['message']['content']

            self.session.evaluation_report = evaluation_text
            self.session.score = avg_score

            tech_qs = [q for q in scored_qs if q.category in ('TECHNICAL', 'CODING')]
            if tech_qs:
                self.session.technical_score = round(sum(q.score for q in tech_qs) / len(tech_qs), 2)

            comm_qs = [q for q in scored_qs if q.category in ('PERSONAL', 'BEHAVIORAL', 'RESUME')]
            if comm_qs:
                self.session.communication_score = round(sum(q.score for q in comm_qs) / len(comm_qs), 2)

            self.session.save()
            print(f"[Agent] Final eval done. Score: {avg_score}/10")
            return evaluation_text

        except Exception as e:
            print(f"[Agent] Final eval error: {e}")

            # Always compute tech/comm scores even in fallback path
            tech_qs = [q for q in scored_qs if q.category in ("TECHNICAL", "CODING")]
            comm_qs = [q for q in scored_qs if q.category in ("PERSONAL", "BEHAVIORAL", "RESUME")]
            tech_score = round(sum(q.score for q in tech_qs) / len(tech_qs), 2) if tech_qs else None
            comm_score = round(sum(q.score for q in comm_qs) / len(comm_qs), 2) if comm_qs else None
            tech_str = f"{tech_score}/10" if tech_score else "N/A"
            comm_str = f"{comm_score}/10" if comm_score else "N/A"

            fallback = (
                f"Evaluation Report for {self.session.candidate_name}\n\n"
                f"1. Overall Summary: Completed with average score {avg_score}/10 across {len(scored_qs)} questions.\n"
                f"2. Technical Rating: {tech_str}\n"
                f"3. Communication Rating: {comm_str}\n"
                f"4. Strengths: Participated in all stages.\n"
                f"5. Areas for Improvement: Provide more detailed answers.\n"
                f"6. Hiring Recommendation: Maybe — Manual review recommended."
            )
            self.session.evaluation_report = fallback
            self.session.score = avg_score
            if tech_score:
                self.session.technical_score = tech_score
            if comm_score:
                self.session.communication_score = comm_score
            self.session.save()
            return fallback