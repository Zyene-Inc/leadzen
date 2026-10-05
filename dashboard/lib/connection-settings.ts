export type Settings = {
  llm: {
    enabled: boolean;
    provider: string;
    model: string;
    base_url: string;
    api_key_configured: boolean;
  };
  lead_finder: {
    provider: "bettercontact";
    api_key_configured: boolean;
  };
  mailbox: {
    transport: string;
    api_url: string;
    smtp_username: string;
    address: string;
    smtp_host: string;
    smtp_port: string;
    imap_host: string;
    imap_port: string;
    signature: string;
    password_configured: boolean;
    api_key_configured: boolean;
    imap_password_configured: boolean;
  };
  settings_key_configured: boolean;
};
export type Credentials = {
  ai: string;
  smtp: string;
  mailApi: string;
  imap: string;
  bettercontact: string;
  clearBettercontact: boolean;
};
export const emptyCredentials: Credentials = {
  ai: "",
  smtp: "",
  mailApi: "",
  imap: "",
  bettercontact: "",
  clearBettercontact: false,
};
export const emptySettings: Settings = {
  llm: {
    enabled: true,
    provider: "groq",
    model: "openai/gpt-oss-120b",
    base_url: "",
    api_key_configured: false,
  },
  lead_finder: {
    provider: "bettercontact",
    api_key_configured: false,
  },
  mailbox: {
    transport: "smtp",
    api_url: "",
    smtp_username: "",
    address: "",
    smtp_host: "",
    smtp_port: "587",
    imap_host: "",
    imap_port: "993",
    signature: "",
    password_configured: false,
    api_key_configured: false,
    imap_password_configured: false,
  },
  settings_key_configured: false,
};
export function settingsBody(settings: Settings, credentials: Credentials) {
  return {
    llm: { ...settings.llm, api_key: credentials.ai },
    lead_finder: {
      provider: "bettercontact",
      api_key: credentials.bettercontact,
      clear_api_key: credentials.clearBettercontact,
    },
    mailbox: {
      ...settings.mailbox,
      password: credentials.smtp,
      api_key: credentials.mailApi,
      imap_password: credentials.imap,
    },
  };
}
