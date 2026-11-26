export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export type ApplicationStatus = "saved" | "applied" | "interviewing" | "offer" | "rejected" | "withdrawn";

export type Database = {
  public: {
    Tables: {
      jobs: {
        Row: { id: string; identity: string; company: string; title: string; location: string; url: string; terms: string[]; source: string; category: string | null; first_seen: string; last_seen: string; closed_at: string | null };
        Insert: { id: string; identity: string; company: string; title: string; location?: string; url: string; terms?: string[]; source: string; category?: string | null; first_seen?: string; last_seen?: string; closed_at?: string | null };
        Update: { id?: string; identity?: string; company?: string; title?: string; location?: string; url?: string; terms?: string[]; source?: string; category?: string | null; first_seen?: string; last_seen?: string; closed_at?: string | null };
        Relationships: [];
      };
      default_top_companies: { Row: { name: string }; Insert: { name: string }; Update: { name?: string }; Relationships: [] };
      profiles: {
        Row: { user_id: string; display_name: string | null; discord_user_id: string | null; email: string | null; notify_dm: boolean; notify_email: boolean; created_at: string };
        Insert: { user_id: string; display_name?: string | null; discord_user_id?: string | null; email?: string | null; notify_dm?: boolean; notify_email?: boolean; created_at?: string };
        Update: { display_name?: string | null; notify_dm?: boolean; notify_email?: boolean };
        Relationships: [];
      };
      user_preferences: {
        Row: { user_id: string; roles: string[]; locations: string[]; terms: string[]; exclude_roles: string[]; categories: string[]; keep_unknown_terms: boolean; only_top_companies: boolean; follow_up_days: number; updated_at: string };
        Insert: { user_id: string; roles?: string[]; locations?: string[]; terms?: string[]; exclude_roles?: string[]; categories?: string[]; keep_unknown_terms?: boolean; only_top_companies?: boolean; follow_up_days?: number; updated_at?: string };
        Update: { roles?: string[]; locations?: string[]; terms?: string[]; exclude_roles?: string[]; categories?: string[]; keep_unknown_terms?: boolean; only_top_companies?: boolean; follow_up_days?: number; updated_at?: string };
        Relationships: [];
      };
      user_top_company_overrides: { Row: { user_id: string; company: string; action: "add" | "remove" }; Insert: { user_id: string; company: string; action: "add" | "remove" }; Update: { action?: "add" | "remove" }; Relationships: [] };
      user_jobs: {
        Row: { user_id: string; job_id: string; status: ApplicationStatus; saved_at: string; applied_at: string | null; follow_up_on: string | null; notes: string | null; source: "web" | "discord_pin" | "discord_applied" | "import"; updated_at: string };
        Insert: { user_id: string; job_id: string; status?: ApplicationStatus; saved_at?: string; applied_at?: string | null; follow_up_on?: string | null; notes?: string | null; source?: "web" | "discord_pin" | "discord_applied" | "import"; updated_at?: string };
        Update: { status?: ApplicationStatus; applied_at?: string | null; follow_up_on?: string | null; notes?: string | null; source?: "web" | "discord_pin" | "discord_applied" | "import"; updated_at?: string };
        Relationships: [{ foreignKeyName: "user_jobs_job_id_fkey"; columns: ["job_id"]; isOneToOne: false; referencedRelation: "jobs"; referencedColumns: ["id"] }];
      };
      user_job_events: { Row: { id: number; user_id: string; job_id: string; status: ApplicationStatus; at: string }; Insert: { id?: number; user_id: string; job_id: string; status: ApplicationStatus; at?: string }; Update: { [key: string]: never }; Relationships: [] };
      notifications: { Row: { user_id: string; job_id: string; channel: string; status: string; attempts: number; error: string | null; created_at: string; sent_at: string | null }; Insert: { [key: string]: never }; Update: { [key: string]: never }; Relationships: [] };
      state_docs: { Row: { name: string; kind: string; value: Json | null; updated_at: string }; Insert: { [key: string]: never }; Update: { [key: string]: never }; Relationships: [] };
      state_parts: { Row: { name: string; key: string; value: Json; updated_at: string }; Insert: { [key: string]: never }; Update: { [key: string]: never }; Relationships: [] };
    };
    Views: {
      user_top_companies: { Row: { user_id: string; company: string }; Relationships: [] };
    };
    Functions: { [_ in never]: never };
    Enums: { application_status: ApplicationStatus };
    CompositeTypes: { [_ in never]: never };
  };
};
