<?php
/**
 * Cold Email AI Optimizer - Seed Templates
 *
 * 10 industry-specific seed templates based on best practices.
 * These bootstrap the first iteration before Claude starts generating.
 * All use timeline-based hooks where applicable, 6-8 sentences, single CTA.
 */

function get_seed_templates(): array {
    return [
        'saas' => [
            [
                'subject_line' => '{company} scaling question?',
                'body' => 'Hi {first_name}, I noticed {company} just {recent_event} — congrats on the momentum. When teams scale that quickly, {pain_point} tends to become the bottleneck that slows everything down. We built a solution that helped three similar SaaS companies cut that friction by 40% in under 90 days. One of them went from 2-week deployment cycles to shipping daily. I put together a quick breakdown specific to {company} that might be worth a look. Open for a 10-minute chat this week?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 8am',
            ],
            [
                'subject_line' => 'quick thought on {recent_event}',
                'body' => 'Hey {first_name}, saw the news about {recent_event} at {company}. That kind of growth usually creates interesting challenges around {pain_point}. We recently helped a team in a similar stage reduce their operational overhead by 35% — without adding headcount. The approach was surprisingly simple and took about 3 weeks to implement. Happy to share the playbook if it sounds relevant. Worth a quick call Tuesday or Wednesday?',
                'hook_type' => 'timeline',
                'send_time' => 'Wednesday 9am',
            ],
        ],
        'real_estate' => [
            [
                'subject_line' => '{first_name}, listings question',
                'body' => 'Hi {first_name}, I saw {company} just closed on {recent_event} — nice work. A lot of agents in your market are telling us {pain_point} is eating into their pipeline right now. We put together a system that helped one brokerage in a similar market generate 23 qualified leads in their first month. The approach works particularly well for agents handling {company}\'s volume. I recorded a 2-minute walkthrough showing exactly how it works. Mind if I send it over?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 7am',
            ],
            [
                'subject_line' => 'saw your {recent_event}',
                'body' => 'Hey {first_name}, congrats on {recent_event}. That part of the market is heating up and I imagine {pain_point} is top of mind. We work with about a dozen brokerages your size and the ones growing fastest all share one thing — they automated their follow-up within 5 minutes of inquiry. One agent told us it doubled her conversion rate in 60 days. Would it be worth exploring how that might look for {company}? Free Thursday morning?',
                'hook_type' => 'timeline',
                'send_time' => 'Thursday 8am',
            ],
        ],
        'recruiting' => [
            [
                'subject_line' => '{company} hiring push?',
                'body' => 'Hi {first_name}, noticed {company} posted {recent_event} — looks like you\'re building fast. When teams hire at that pace, {pain_point} usually becomes the biggest drag on time-to-fill. We helped a similar-sized recruiting team cut their average fill time from 45 days to 22 days last quarter. The approach focused on one specific bottleneck that most teams overlook. Would it make sense to share what worked? Open for a quick chat this week?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 9am',
            ],
            [
                'subject_line' => 'thought on {pain_point}',
                'body' => 'Hey {first_name}, I keep hearing from talent teams that {pain_point} is the number one challenge this quarter. Your competitor just solved it by changing one thing in their process — and their candidate response rate jumped 3x. Given the roles {company} is filling right now, this approach could save your team 15+ hours per week. I can share the exact framework in a 10-minute call. Worth a look?',
                'hook_type' => 'problem',
                'send_time' => 'Wednesday 8am',
            ],
        ],
        'marketing' => [
            [
                'subject_line' => '{first_name}, ROI question',
                'body' => 'Hi {first_name}, saw that {company} recently {recent_event}. Agencies at your stage often struggle with {pain_point} — especially when scaling past the founder-led sales model. We work with 8 agencies your size and the common thread among the ones growing 40%+ YoY is a specific client acquisition system. One agency owner told us it reduced their CAC by half in 90 days. I put together a breakdown that maps to {company}\'s positioning. Interested in taking a look?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 10am',
            ],
            [
                'subject_line' => 'quick {company} idea',
                'body' => 'Hey {first_name}, most agency owners I talk to say {pain_point} is their biggest bottleneck right now. What\'s interesting is the agencies winning new clients fastest aren\'t doing more outreach — they\'re doing smarter outreach. One specific tactic helped an agency similar to {company} land 4 new retainer clients in 6 weeks. The whole approach fits into existing workflows without adding overhead. Worth 10 minutes to walk through it?',
                'hook_type' => 'problem',
                'send_time' => 'Wednesday 9am',
            ],
        ],
        'consulting' => [
            [
                'subject_line' => '{first_name}, pipeline thought',
                'body' => 'Hi {first_name}, I noticed {company} just {recent_event} — that\'s a strong signal in the market. Consulting firms at your level often find {pain_point} becomes the constraint on growth. We helped a management consulting firm with a similar profile add $2M to their pipeline in one quarter using a focused approach. It didn\'t require hiring more business development staff. Would it make sense to compare notes? I\'m free Tuesday or Wednesday morning.',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 8am',
            ],
            [
                'subject_line' => 'saw {recent_event}',
                'body' => 'Hey {first_name}, congrats on {recent_event}. Given where {company} is headed, I imagine {pain_point} is becoming a priority. Three consulting firms we work with solved this by implementing one systematic change — their partner utilization went up 30% and they stopped leaving revenue on the table. The framework took about 4 weeks to fully deploy. Interested in seeing how it might apply to {company}?',
                'hook_type' => 'timeline',
                'send_time' => 'Thursday 9am',
            ],
        ],
        'finance' => [
            [
                'subject_line' => '{first_name}, compliance thought',
                'body' => 'Hi {first_name}, I noticed {company} recently {recent_event}. Financial services firms navigating that transition often hit a wall with {pain_point}. We helped a similar firm reduce their compliance processing time by 60% while actually improving accuracy. The approach worked because it addressed the root bottleneck rather than adding more people to the process. I have a short case study that mirrors {company}\'s situation. Worth a 10-minute review?',
                'hook_type' => 'timeline',
                'send_time' => 'Wednesday 8am',
            ],
            [
                'subject_line' => 'question about {pain_point}',
                'body' => 'Hey {first_name}, {pain_point} keeps coming up in every conversation I have with finance leaders this quarter. One CFO told me they were spending 20 hours per week just managing the problem — until they found a way to automate 80% of it. The solution paid for itself in the first month. Given {company}\'s scale, the impact could be even larger. Would it be worth a quick conversation this week?',
                'hook_type' => 'problem',
                'send_time' => 'Tuesday 9am',
            ],
        ],
        'healthcare' => [
            [
                'subject_line' => '{first_name}, patient flow idea',
                'body' => 'Hi {first_name}, saw that {company} just {recent_event}. Healthcare organizations in that growth phase often find {pain_point} becomes a major constraint. We helped a practice group similar to yours increase patient throughput by 25% without adding clinical staff. The key was addressing one workflow bottleneck that most administrators don\'t realize is costing them. I put together a brief overview specific to {company}\'s setup. Open to a quick look?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 8am',
            ],
            [
                'subject_line' => 'quick thought for {company}',
                'body' => 'Hey {first_name}, healthcare administrators I work with keep flagging {pain_point} as their top priority this year. One medical group found a solution that cut their admin burden by 40% and improved patient satisfaction scores at the same time. The implementation took 3 weeks and didn\'t disrupt existing workflows. Based on {company}\'s size, the results could be significant. Worth 10 minutes to walk through the approach?',
                'hook_type' => 'problem',
                'send_time' => 'Wednesday 9am',
            ],
        ],
        'legal' => [
            [
                'subject_line' => '{first_name}, intake question',
                'body' => 'Hi {first_name}, I noticed {company} recently {recent_event}. Law firms at your stage often find {pain_point} is the hidden bottleneck limiting growth. We worked with a similar firm that was losing 30% of qualified leads to slow intake processing. After implementing one systematic change, their conversion rate doubled in 60 days. The partners said it was the highest-ROI change they made all year. Interested in seeing how it might apply to {company}?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 8am',
            ],
            [
                'subject_line' => 'thought on {pain_point}',
                'body' => 'Hey {first_name}, managing partners keep telling me {pain_point} is the challenge keeping them up at night. One firm found that addressing it systematically freed up 10+ billable hours per attorney per month. The approach focused on eliminating one specific type of administrative drag. Given {company}\'s practice areas, the impact could be substantial. Worth comparing notes over a quick call?',
                'hook_type' => 'problem',
                'send_time' => 'Wednesday 10am',
            ],
        ],
        'ecommerce' => [
            [
                'subject_line' => '{company} growth question?',
                'body' => 'Hi {first_name}, noticed {company} just {recent_event} — impressive traction. E-commerce brands scaling at your pace often hit a wall with {pain_point}. We helped a DTC brand with similar revenue cut their customer acquisition cost by 35% in one quarter. The approach was counterintuitive — they actually reduced their ad spend and got more customers. I put together a quick analysis based on {company}\'s current positioning. Worth a peek?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 9am',
            ],
            [
                'subject_line' => 'idea for {recent_event}',
                'body' => 'Hey {first_name}, congrats on {recent_event}. The brands growing fastest right now are solving {pain_point} differently than everyone else. One founder told me changing a single part of their checkout flow increased revenue 22% with zero additional traffic. Took a developer about a week to implement. Based on what I can see about {company}, there might be a similar opportunity. Open for a 10-minute chat this week?',
                'hook_type' => 'timeline',
                'send_time' => 'Thursday 8am',
            ],
        ],
        'construction' => [
            [
                'subject_line' => '{first_name}, project question',
                'body' => 'Hi {first_name}, I saw {company} just won {recent_event} — congrats on the project. General contractors managing that volume often struggle with {pain_point}. We helped a similar firm reduce project delays by 40% and improve their bid win rate at the same time. The approach was simple — one change to how they tracked and communicated across subcontractors. I have a quick overview that maps to {company}\'s operations. Worth 10 minutes?',
                'hook_type' => 'timeline',
                'send_time' => 'Tuesday 7am',
            ],
            [
                'subject_line' => 'thought on {pain_point}',
                'body' => 'Hey {first_name}, every GC I talk to says {pain_point} is the number one thing eating into their margins right now. One contractor found a way to solve it that saved them $200K in the first year. The whole thing took about 2 weeks to set up and his team adopted it immediately. Given the size of projects {company} handles, the savings could be even bigger. Interested in hearing how they did it?',
                'hook_type' => 'problem',
                'send_time' => 'Wednesday 7am',
            ],
        ],
    ];
}

function get_industry_keys(): array {
    return array_keys(INDUSTRY_BENCHMARKS);
}

function pick_industries(int $iteration_num, int $count = 3): array {
    $all = get_industry_keys();
    $total = count($all);

    // Rotate through industries deterministically
    $start = (($iteration_num - 1) * $count) % $total;
    $selected = [];

    for ($i = 0; $i < $count; $i++) {
        $selected[] = $all[($start + $i) % $total];
    }

    return $selected;
}
