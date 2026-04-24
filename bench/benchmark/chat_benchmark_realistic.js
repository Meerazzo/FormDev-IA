import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const API_KEY = __ENV.API_KEY || "";
const MODEL = __ENV.MODEL || "Qwen/Qwen2.5-7B-Instruct-AWQ";

export const options = {
  scenarios: {
    chat_load: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 5),
      duration: __ENV.DURATION || "1m",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<20000"],
  },
};

const scenarios = [
  {
    name: "reformulation_catalogue_sport",
    payload: {
      model: MODEL,
      system_prompt:
        "Tu es un assistant de reformulation en français. Tu reformules les textes dans un style professionnel, fluide, clair et naturel. Tu conserves le sens initial, sans ajouter d'information non présente.",
      messages: [
        {
          role: "user",
          content:
            "Reformule ce texte pour une brochure de formation. Réponds uniquement avec le texte final, sans commentaire ni introduction : Cette formation permet de voir plusieurs points pour apprendre à encadrer des séances de renforcement musculaire, avec une partie pratique, des conseils de posture et des idées d'exercices adaptables à différents publics.",
        },
      ],
      max_tokens: 180,
      temperature: 0.2,
      top_p: 0.9,
      post_correction: false,
    },
  },
  {
    name: "reformulation_technique_industrielle",
    payload: {
      model: MODEL,
      system_prompt:
        "Tu es un assistant de reformulation professionnelle. Tu clarifies les formulations, améliores la fluidité et corriges les maladresses, sans modifier le fond technique.",
      messages: [
        {
          role: "user",
          content:
            "Reformule ce texte dans un style plus structuré et professionnel. Réponds uniquement avec le texte final, sans commentaire ni introduction : La formation sert à revoir les bases de maintenance de premier niveau sur des équipements industriels, avec de la prévention sécurité, des contrôles visuels et quelques manipulations simples pour éviter les pannes courantes.",
        },
      ],
      max_tokens: 180,
      temperature: 0.2,
      top_p: 0.9,
      post_correction: false,
    },
  },
  {
    name: "summary_safety_training",
    payload: {
      model: MODEL,
      system_prompt:
        "Tu es un assistant de synthèse. Tu produis des résumés clairs, structurés et professionnels en français. Tu conserves uniquement les informations essentielles.",
      messages: [
        {
          role: "user",
          content:
            "Résume ce texte en 3 phrases claires. Réponds uniquement avec le résumé final, sans commentaire ni introduction : Cette formation sensibilise les participants aux risques liés au travail en hauteur. Elle présente les règles de sécurité, les équipements de protection individuelle, les bonnes pratiques de vérification du matériel et les réflexes à adopter avant toute intervention. Des cas concrets et des mises en situation permettent de relier les apports théoriques à la réalité du terrain.",
        },
      ],
      max_tokens: 140,
      temperature: 0.2,
      top_p: 0.9,
      post_correction: false,
    },
  },
  {
    name: "content_enrichment_medico_social",
    payload: {
      model: MODEL,
      system_prompt:
        "Tu es un assistant de rédaction pour des catalogues de formation. Tu développes les intitulés en paragraphes professionnels, fluides, précis et directement réutilisables.",
      messages: [
        {
          role: "user",
          content:
            "Développe cet intitulé sous la forme d'un paragraphe de présentation de formation. Réponds uniquement avec le paragraphe final, sans commentaire ni introduction : Prévenir l'épuisement professionnel dans les métiers de l'accompagnement",
        },
      ],
      max_tokens: 220,
      temperature: 0.3,
      top_p: 0.9,
      post_correction: false,
    },
  },
  {
    name: "conversation_with_history_project_management",
    payload: {
      model: MODEL,
      system_prompt:
        "Tu es un assistant de rédaction professionnelle. Tu réponds en français clair, synthétique et réutilisable en contexte formation.",
      messages: [
        {
          role: "user",
          content:
            "Résume ce texte en 4 phrases : Cette formation en gestion de projet permet aux participants de comprendre les grandes étapes de cadrage, de planification, de suivi et de clôture d'un projet. Elle aborde également la coordination des acteurs, le suivi des délais, la gestion des priorités et l'anticipation des risques.",
        },
        {
          role: "assistant",
          content:
            "Cette formation présente les principales étapes de la gestion de projet, du cadrage à la clôture. Elle aide à structurer le suivi des délais, des priorités et des risques. Elle met également l'accent sur la coordination des acteurs impliqués. L'ensemble vise à renforcer la conduite opérationnelle des projets.",
        },
        {
          role: "user",
          content:
            "Fais maintenant une version plus concise en 2 phrases. Réponds uniquement avec le texte final, sans commentaire ni introduction.",
        },
      ],
      max_tokens: 100,
      temperature: 0.2,
      top_p: 0.9,
      post_correction: false,
    },
  },
  {
    name: "post_correction_custom_prompt",
    payload: {
      model: MODEL,
      system_prompt:
        "Tu es un assistant de reformulation professionnelle. Réécris le texte dans un style clair et professionnel.",
      messages: [
        {
          role: "user",
          content:
            "Reformule ce texte : Cette formation permet aux équipes techniques de mieux comprendre les bases du câblage réseau, les points de vigilance lors des installations et les erreurs fréquentes à éviter sur le terrain.",
        },
      ],
      max_tokens: 180,
      temperature: 0.2,
      top_p: 0.9,
      post_correction: true,
      post_correction_prompt:
        "Tu es un correcteur linguistique. Corrige l'orthographe, la grammaire et la syntaxe. Améliore légèrement la fluidité sans changer le sens, sans raccourcir fortement et sans ajouter d'information.",
    },
  },
];

function pickScenario() {
  return scenarios[Math.floor(Math.random() * scenarios.length)];
}

export default function () {
  const scenario = pickScenario();

  const res = http.post(`${BASE_URL}/v1/chat`, JSON.stringify(scenario.payload), {
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    timeout: "120s",
    tags: {
      scenario_name: scenario.name,
    },
  });

  check(res, {
    "status 200": (r) => r.status === 200,
    "response has content": (r) => {
      if (r.status !== 200) return false;
      try {
        const body = JSON.parse(r.body);
        return !!body.content;
      } catch {
        return false;
      }
    },
  });

  if (res.status !== 200) {
    console.log(`[${scenario.name}] status=${res.status} body=${res.body}`);
  }

  sleep(1);
}