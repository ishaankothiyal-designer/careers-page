"""Illustrative regional job data. These records are not real vacancies."""
import hashlib

SEED_VERSION = 'regional-demo-v2'
INDIA_REGIONS = (
    ('Andhra Pradesh', 'Vijayawada'), ('Arunachal Pradesh', 'Itanagar'),
    ('Assam', 'Guwahati'), ('Bihar', 'Patna'), ('Chhattisgarh', 'Raipur'),
    ('Goa', 'Panaji'), ('Gujarat', 'Ahmedabad'), ('Haryana', 'Gurugram'),
    ('Himachal Pradesh', 'Shimla'), ('Jharkhand', 'Ranchi'), ('Karnataka', 'Bengaluru'),
    ('Kerala', 'Kochi'), ('Madhya Pradesh', 'Indore'), ('Maharashtra', 'Pune'),
    ('Manipur', 'Imphal'), ('Meghalaya', 'Shillong'), ('Mizoram', 'Aizawl'),
    ('Nagaland', 'Kohima'), ('Odisha', 'Bhubaneswar'), ('Punjab', 'Ludhiana'),
    ('Rajasthan', 'Jaipur'), ('Sikkim', 'Gangtok'), ('Tamil Nadu', 'Chennai'),
    ('Telangana', 'Hyderabad'), ('Tripura', 'Agartala'), ('Uttar Pradesh', 'Noida'),
    ('Uttarakhand', 'Dehradun'), ('West Bengal', 'Kolkata'),
    ('Andaman and Nicobar Islands', 'Sri Vijaya Puram'), ('Chandigarh', 'Chandigarh'),
    ('Dadra and Nagar Haveli and Daman and Diu', 'Silvassa'), ('Delhi', 'New Delhi'),
    ('Jammu and Kashmir', 'Srinagar'), ('Ladakh', 'Leh'), ('Lakshadweep', 'Kavaratti'),
    ('Puducherry', 'Puducherry'),
)
AUSTRALIA_REGIONS = (
    ('New South Wales', 'Sydney'), ('Victoria', 'Melbourne'), ('Queensland', 'Brisbane'),
    ('South Australia', 'Adelaide'), ('Western Australia', 'Perth'), ('Tasmania', 'Hobart'),
    ('Australian Capital Territory', 'Canberra'), ('Northern Territory', 'Darwin'),
)
UAE_REGIONS = (
    ('Abu Dhabi', 'Abu Dhabi'), ('Dubai', 'Dubai'), ('Sharjah', 'Sharjah'),
    ('Ajman', 'Ajman'), ('Umm Al Quwain', 'Umm Al Quwain'),
    ('Ras Al Khaimah', 'Ras Al Khaimah'), ('Fujairah', 'Fujairah'),
)
# Problem, team, work mode, responsibility, relevant experience, first deliverable.
PROBLEMS = (
    ('Design a clearer buying journey', 'Design', 'Hybrid', 'Map confusing steps in a sample buying journey and prototype clearer choices.', 'Product design, user research, and accessible interface design.', 'Test a buying-journey prototype and document the decisions that make it clearer.'),
    ('Build useful customer tools', 'Engineering', 'Remote', 'Build and test a small tool that helps customers compare their options.', 'Web engineering, testing, and communicating technical tradeoffs.', 'Ship a tested comparison-tool prototype with a clear handover.'),
    ('Simplify inspection workflows', 'Operations', 'On-site', 'Observe a simulated inspection handoff and make the checklist easier to follow.', 'Process improvement, clear documentation, and cross-team collaboration.', 'Pilot an inspection checklist and share what the team learned.'),
    ('Make support easier to navigate', 'Customer Experience', 'Hybrid', 'Find recurring questions in sample support cases and improve the response journey.', 'Customer support, thoughtful writing, and problem-solving.', 'Create a support guide and test how easily a teammate can use it.'),
    ('Turn signals into better decisions', 'Data', 'Remote', 'Explore a synthetic customer dataset and explain which questions it can answer.', 'Data analysis, SQL, and communicating uncertainty.', 'Build a reproducible analysis using synthetic data and present its limitations.'),
    ('Help teams learn through work', 'People', 'Hybrid', 'Design a sample onboarding path with practical work and regular feedback.', 'Learning design, facilitation, and thoughtful collaboration.', 'Pilot an onboarding exercise and improve it using participant feedback.'),
    ('Make vehicle information clearer', 'Design', 'Hybrid', 'Prototype a vehicle-information page that helps people understand unfamiliar details.', 'Information design, accessibility, and user testing.', 'Test an information-page prototype and capture the next design decisions.'),
    ('Improve service reliability', 'Engineering', 'Remote', 'Create a demo service with readable error handling and useful operational checks.', 'Backend engineering, debugging, and reliable software delivery.', 'Demonstrate a resilient sample service and document its failure handling.'),
    ('Improve local handoffs', 'Operations', 'On-site', 'Map a simulated local handoff and identify where responsibilities become unclear.', 'Operations planning, coordination, and practical process design.', 'Pilot a handoff plan with explicit ownership and a review routine.'),
    ('Listen to customer friction', 'Customer Experience', 'Hybrid', 'Review fictional customer stories and translate repeated friction into clear actions.', 'Customer research, empathy, and concise written communication.', 'Present an evidence-based improvement plan using fictional research cases.'),
    ('Build understandable reporting', 'Data', 'Remote', 'Create a sample report that shows both useful signals and the limits of its data.', 'Analytics, data visualization, and documentation.', 'Deliver a reporting prototype with a glossary and clear caveats.'),
    ('Create better feedback habits', 'People', 'Hybrid', 'Design a practical feedback exercise that teams can use during project reviews.', 'Facilitation, people programs, and constructive communication.', 'Run a sample project review and refine its feedback prompts.'),
)


def demo_jobs():
    """Return exactly 120 deterministic demo jobs across 51 regions."""
    jobs = []
    for country, regions, per_region in (
        ('India', INDIA_REGIONS, 2), ('Australia', AUSTRALIA_REGIONS, 3), ('UAE', UAE_REGIONS, 3)
    ):
        for region_index, (state, city) in enumerate(regions):
            count = per_region + (1 if country == 'UAE' and state in ('Dubai', 'Abu Dhabi', 'Sharjah') else 0)
            for slot in range(count):
                problem, team, mode, responsibility, experience, deliverable = PROBLEMS[(region_index * per_region + slot) % len(PROBLEMS)]
                key = f'{SEED_VERSION}|{country}|{state}|{slot}'
                jobs.append({
                    'id': 'demo-' + hashlib.sha256(key.encode()).hexdigest()[:24],
                    'title': f'Builder – {problem} · {city}',
                    'team': team, 'location': city, 'country': country, 'state': state,
                    'work_mode': mode, 'employment_type': 'Full-time',
                    'description': f'Illustrative demo role for {city}, {state}, {country}. This is sample content for testing the careers and admin flows, not an active vacancy or a claim that an office exists here. Explore how a builder could help {problem.lower()}.',
                    'responsibilities': f'{responsibility}\nCollaborate openly with the sample {team.lower()} team.\nDocument decisions, tradeoffs, and what you learn.',
                    'requirements': f'{experience}\nCuriosity, clear communication, and willingness to learn through work.\nAll requirements are illustrative and do not describe a real hiring process.',
                    'first_90_days': f'Sample plan for {city}: understand the problem and local context, choose a focused experiment with the team, then {deliverable[0].lower() + deliverable[1:]}',
                    'status': 'published',
                })
    return jobs
