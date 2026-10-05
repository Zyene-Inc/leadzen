export type ProductTourState = {
  tourStarted: boolean;
  currentStep: string;
  tourCompleted: boolean;
  tourSkipped: boolean;
};
export type TourAction = "start" | "progress" | "complete" | "skip";
export type StoredTour = { tour: ProductTourState; pending: boolean; action: TourAction };
export const tourStorageKey = (userId: number) => `leadzen.product-tour.v1.${userId}`;
export const tourIsActive = (tour: ProductTourState) => tour.tourStarted && !tour.tourCompleted && !tour.tourSkipped;
export function readPendingTour(userId: number): StoredTour | null {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(tourStorageKey(userId)) ?? "null");
    if (!data || typeof data !== "object") return null;
    const value = data as StoredTour;
    const tour = value.tour;
    if (!value.pending || !["start", "progress", "complete", "skip"].includes(value.action) || !tour || typeof tour.currentStep !== "string" || !/^[a-z][a-z0-9-]{0,63}$/.test(tour.currentStep)) return null;
    if (![tour.tourStarted, tour.tourCompleted, tour.tourSkipped].every((flag) => typeof flag === "boolean")) return null;
    return value;
  } catch { return null; }
}
export function storeTour(userId: number, value: StoredTour) {
  try { localStorage.setItem(tourStorageKey(userId), JSON.stringify(value)); } catch { /* Account persistence still works when browser storage is unavailable. */ }
}
