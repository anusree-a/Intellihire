from django.core.management.base import BaseCommand
from interviews.models import SubscriptionPlan


class Command(BaseCommand):
    help = 'Seed subscription plans into the database'

    def handle(self, *args, **options):
        plans = [
            {
                'name': 'basic',
                'price': '20.00',
                'interviews_per_month': 10,
                'ai_features': False,
                'analytics': False,
                'priority_support': False,
                'description': 'Perfect for small teams just starting out.',
            },
            {
                'name': 'professional',
                'price': '50.00',
                'interviews_per_month': 50,
                'ai_features': True,
                'analytics': False,
                'priority_support': False,
                'description': 'Ideal for growing companies with active hiring.',
            },
            {
                'name': 'premium',
                'price': '150.00',
                'interviews_per_month': 200,
                'ai_features': True,
                'analytics': True,
                'priority_support': True,
                'description': 'Full-featured plan for enterprise hiring needs.',
            },
        ]

        for p in plans:
            obj, created = SubscriptionPlan.objects.update_or_create(
                name=p['name'], defaults=p
            )
            status = 'Created' if created else 'Updated'
            self.stdout.write(f"  {status}: {obj}")

        self.stdout.write(self.style.SUCCESS('Plans seeded successfully!'))