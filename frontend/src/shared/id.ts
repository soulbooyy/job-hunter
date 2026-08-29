export type IdFactory = () => string;

export const randomId: IdFactory = () => crypto.randomUUID();
