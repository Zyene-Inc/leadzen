export type TourStep = {
  id: string;
  route: string;
  target: string;
  title: string;
  body: string;
  action?: {
    label: string;
    kind: "click";
    success?: string;
    absent?: string;
    route?: string;
  };
  prepare?: { open: string; visible: string };
  placement?: "right" | "bottom" | "top";
};

const contactForm = '[data-tour="contact-form"]';
const scheduleEditor = '[data-tour="schedule-editor"]';

// Targets belong to the live product. Preparation opens only existing, reversible
// forms; no tour step creates records, calls AI, buys emails or sends messages.
export const productTourSteps: readonly TourStep[] = [
  {
    id: "welcome",
    route: "/",
    target: '[data-tour="home-attention"]',
    title: "Welcome to LeadZen",
    body: "Start here for drafts to review, new replies and work that needs your attention. Let’s explore your workspace.",
    placement: "bottom",
  },
  {
    id: "open-leads",
    route: "/",
    target: '[data-tour="nav-contacts"]',
    title: "Your leads live here",
    body: "Find people, import a list or add a contact in one place.",
    action: { kind: "click", label: "Click Leads", route: "/contacts" },
    placement: "right",
  },
  {
    id: "add-contact",
    route: "/contacts",
    target: '[data-tour="contact-add"]',
    title: "Add someone you know",
    body: "Open the real contact form to see the details you can save.",
    action: { kind: "click", label: "Click Add contact", success: contactForm },
    placement: "bottom",
  },
  {
    id: "contact-details",
    route: "/contacts",
    target: '[data-tour="contact-email"]',
    title: "Keep useful contact details",
    body: "Add an email, name and company. Save only real contacts; you don’t need to enter anything for this tour.",
    prepare: { open: '[data-tour="contact-add"]', visible: contactForm },
    placement: "bottom",
  },
  {
    id: "close-contact",
    route: "/contacts",
    target: '[data-tour="contact-close"]',
    title: "Return to your leads",
    body: "Close this preview of the form to continue exploring.",
    action: { kind: "click", label: "Click Close form", absent: contactForm },
    prepare: { open: '[data-tour="contact-add"]', visible: contactForm },
    placement: "bottom",
  },
  {
    id: "review-outreach",
    route: "/outreach",
    target: '[data-tour="outreach-flow"]',
    title: "From leads to outreach",
    body: "Select leads, review messages and confirm sending here. Add follow-ups when needed, or use Ask LeadZen for help with a draft.",
    placement: "bottom",
  },
  {
    id: "open-inbox",
    route: "/outreach",
    target: '[data-tour="nav-inbox"]',
    title: "Keep conversations together",
    body: "Your saved replies and conversation history are in Inbox.",
    action: { kind: "click", label: "Click Inbox", route: "/inbox" },
    placement: "right",
  },
  {
    id: "check-replies",
    route: "/inbox",
    target: '[data-tour="inbox-replies"]',
    title: "Check for new replies",
    body: "This checks your connected mailbox after approval. You can review a reply before sending; no check is needed for this tour.",
    placement: "bottom",
  },
  {
    id: "open-settings",
    route: "/inbox",
    target: '[data-tour="nav-settings"]',
    title: "Make the workspace yours",
    body: "Manage connections, your offer, audience and sending hours in Settings.",
    action: { kind: "click", label: "Click Settings", route: "/settings" },
    placement: "right",
  },
  {
    id: "edit-hours",
    route: "/settings",
    target: '[data-tour="schedule-edit"]',
    title: "Choose your outreach hours",
    body: "Open Sending hours to see your weekly schedule.",
    action: { kind: "click", label: "Click Edit", success: scheduleEditor },
    placement: "bottom",
  },
  {
    id: "schedule-details",
    route: "/settings",
    target: '[data-tour="schedule-fields"]',
    title: "One schedule, New York time",
    body: "Choose weekly days and start/end times. Daily Autopilot finds leads at the start time. Sending follows this window; changing it needs a new approval.",
    prepare: { open: '[data-tour="schedule-edit"]', visible: scheduleEditor },
    placement: "top",
  },
  {
    id: "close-hours",
    route: "/settings",
    target: '[data-tour="schedule-close"]',
    title: "Keep your current schedule",
    body: "Close the editor to continue without saving changes.",
    action: { kind: "click", label: "Click Close", absent: scheduleEditor },
    prepare: { open: '[data-tour="schedule-edit"]', visible: scheduleEditor },
    placement: "bottom",
  },
  {
    id: "chat-help",
    route: "/chat",
    target: '[data-tour="chat-composer"]',
    title: "Ask LeadZen as you work",
    body: "Ask for help with leads, drafts or replies in this same workspace. AI usage may incur charges. Sending, email purchases and mailbox checks require approval.",
    placement: "top",
  },
  {
    id: "ready",
    route: "/settings",
    target: '[data-tour="tour-restart"]',
    title: "You’re ready to go",
    body: "Start with your leads or the attention list on Home. You can take this tour again from Settings whenever you need it.",
    placement: "bottom",
  },
];
