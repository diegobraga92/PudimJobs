import type { NavigatorScreenParams } from '@react-navigation/native';

export type AuthStackParamList = {
  Login: undefined;
};

export type JobsStackParamList = {
  JobList: undefined;
  JobDetail: { id: string };
};

export type ApplicationsStackParamList = {
  ApplicationList: undefined;
  ApplicationDetail: { id: string };
  /** Editor for one tailored CV artifact (never the master CV — ADR 016). */
  TailoredCvEditor: { id: string };
};

export type AppDrawerParamList = {
  Jobs: NavigatorScreenParams<JobsStackParamList>;
  Sources: undefined;
  MasterCv: undefined;
  Applications: NavigatorScreenParams<ApplicationsStackParamList>;
  Alerts: undefined;
  Notifications: undefined;
  Admin: undefined;
};

export type RootParamList = {
  Auth: NavigatorScreenParams<AuthStackParamList> | undefined;
  App: NavigatorScreenParams<AppDrawerParamList> | undefined;
};
