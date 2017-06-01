import Constants
from Target import TargetType, Target

from abc import ABCMeta, abstractmethod, abstractproperty
import numpy as np
import csv

# Abstract class -- not meant to be directly instantiated. Inherit from this class to implement
# another telescope. See Swope and Nickel implementations...
class Telescope(metaclass=ABCMeta):

	@abstractmethod
	def set_targets(self, targets):
		pass
	
	@abstractmethod
	def get_targets(self):
		pass
	
	@abstractmethod
	def compute_exposures(self):
		pass
	
	@abstractmethod
	def write_schedule(self, observatory_name, obs_date, good_targets):
		pass
	
	def round_to_num(self, round_to_num, input_to_round):
		return int(round_to_num*round(float(input_to_round)/round_to_num))
	
	def time_to_S_N(self, desired_s_n, apparent_mag, zeropoint, px_in_aperature=20):
		term1 = px_in_aperature* desired_s_n**2
		term2 = 0.4*(apparent_mag - zeropoint)
		exp_time = term1*10**term2
		
		return exp_time
	
	def compute_net_priorities(self):
		
		targets = self.get_targets()
		
		total_p = np.sum([t.priority for t in targets])
		print("Total Priority: %s" % total_p)

		total_good_time = np.sum([t.total_observable_min for t in targets])
		print("Total Good Time: %s" % total_good_time)

		total_exp_time = np.sum([t.total_minutes for t in targets])
		print("Total Exposure Time: %s" % total_exp_time)

		total_prob = 0
		if (total_p > 0 and total_good_time > 0 and total_exp_time > 0):
			for t in targets:
				frac_p = float(t.priority) / float(total_p)
				frac_time = float(t.total_observable_min)/float(total_good_time)
				frac_exp_time = (1.0-float(t.total_minutes)/float(total_exp_time))

				if (frac_exp_time == 0.0):
					frac_exp_time = 1.0

				total_prob += frac_p*frac_time*frac_exp_time

			for t in targets:

				frac_p = float(t.priority) / float(total_p)
				frac_time = float(t.total_observable_min)/float(total_good_time)
				frac_exp_time = (1.0-float(t.total_minutes)/float(total_exp_time))

				t.net_priority = (frac_p*frac_time*frac_exp_time)/total_prob
				print("Nat: %s; Net: %0.5f" % (t.priority, t.net_priority))
		else:
			print("No valid targets...")

# Used with Las Campanas Observatory
class Swope(Telescope):
	
	def __init__(self):
		self.targets = None
		self.name = "Swope"
		# Filter name: Zero-point
		self.filters = {
			Constants.u_band:21.083616,
			Constants.B_band:22.885212,
			Constants.V_band:22.992250,
			Constants.g_band:23.66132,
			Constants.r_band:23.320230,
			Constants.i_band:23.131884
		}

		self.exp_funcs = {
			TargetType.Supernova: self.compute_sn_exposure,
			TargetType.Template: self.compute_template_exposure,
			TargetType.Standard: self.compute_standard_exposure,
			TargetType.GW_Static: self.compute_GW_Static_exposure,
			TargetType.GW_Dynamic: self.compute_GW_Dynamic_exposure
		}
	
	def set_targets(self, targets):
		self.targets = targets
		
	def get_targets(self):
		return self.targets

	def compute_GW_Static_exposure(self, GW_Static):
		exposures = {}
		
		exp_time = 120 # default to 120 seconds

		if GW_Static.static_exp_time is not None:
			exp_time = GW_Static.static_exp_time
			
		exposures.update({Constants.g_band: exp_time})
		exposures.update({Constants.i_band: exp_time})
	
		GW_Static.exposures = exposures

	def compute_GW_Dynamic_exposure(self, GW_Dynamic):
		exposures = {}

		App_Mag = GW_Dynamic.est_abs_mag + 5.0*np.log10(GW_Dynamic.host_dist_mpc*1.e6) - 5.0
		#The reason I need to multiply Mpc by 1e5 is the log base 10 implies a need to divide by 10.

		print(App_Mag)
		#We need to compute App_Mag with above function, and assume a Signal to noise value of 30:

		s_to_n = 30.

		g_exp = self.time_to_S_N(s_to_n, App_Mag, self.filters[Constants.g_band])
		i_exp = self.time_to_S_N(s_to_n, App_Mag, self.filters[Constants.i_band])

		exposures.update({Constants.g_band: g_exp})
		exposures.update({Constants.i_band: i_exp})

		GW_Dynamic.exposures = exposures
		
		print(exposures)
	
	def compute_sn_exposure(self, sn):
		exposures = {}
		
		# Compute the current guess at apparent magnitude
		days_from_disc = (sn.obs_date - sn.disc_date).days
		mag_reduction = days_from_disc*0.03
		adj_app_mag = sn.apparent_mag + mag_reduction

		# Change S/N depending on phase...
		s_to_n = 10 # base signal to noise
		if days_from_disc <= 10:
			s_to_n = 30
		elif days_from_disc > 10 and days_from_disc <= 60:
			s_to_n = 20
		
		g_exp = self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.g_band])
		r_exp = self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.r_band])
		i_exp = self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.i_band])
		V_exp = self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.V_band])
		# Specific to Swope -- make Vgri the same length exposure...
		mean_exp = self.round_to_num(Constants.round_to, np.mean([V_exp,g_exp,r_exp,i_exp]))

		exposures.update({Constants.g_band: mean_exp})
		exposures.update({Constants.r_band: mean_exp})
		exposures.update({Constants.i_band: mean_exp})

		# Only include these exposures if a relatively new SN
		if days_from_disc < 60:
			exposures.update({Constants.u_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.u_band]))})
			exposures.update({Constants.B_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.B_band]))})
			exposures.update({Constants.V_band: mean_exp})

		# Finally, don't go less than 45s (~ readout time), don't go more than 600s on Swope
		for key, value in exposures.items():
			if exposures[key] < 45:
				exposures[key] = 45
			elif exposures[key] > 600:
				exposures[key] = 600
			
		sn.exposures = exposures
	
	def compute_standard_exposure(self, std):
		exposures = {}
		s_to_n = 100
		
		# Don't know what the apparent mag should be?
		exposures.update({Constants.u_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.u_band]))})
		exposures.update({Constants.B_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.B_band]))})
		exposures.update({Constants.V_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.V_band]))})
		exposures.update({Constants.g_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.g_band]))})
		exposures.update({Constants.r_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.r_band]))})
		exposures.update({Constants.i_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.i_band]))})
		
		# Finally, for standards round exps and don't go less than 10s, don't go more than 600s on Swope
		# Round to nearest "exp_round_to" secs
		for key, value in exposures.items():
			if exposures[key] < 10:
				exposures[key] = 10
			elif exposures[key] > 600:
				exposures[key] = 600
		
		std.exposures = exposures
		
	def compute_template_exposure(self, tmp):
		exposures = {}
		exposures.update({Constants.u_band: 1800})
		exposures.update({Constants.B_band: 1800})
		exposures.update({Constants.V_band: 1200})
		exposures.update({Constants.g_band: 1200})
		exposures.update({Constants.r_band: 1200})
		exposures.update({Constants.i_band: 1200})
		
		tmp.exposures = exposures
	
	def compute_exposures(self):
		for tgt in self.targets:			
			
			total_possible_time = np.sum(np.where(tgt.raw_airmass_array <= Constants.airmass_threshold)[0])
			
			if total_possible_time > 0:
				tgt.total_observable_min = int(total_possible_time)
				
				self.exp_funcs[tgt.type](tgt) # Sets exposures for each target by target type
				
				# per observatory - LCO Swope
				fudge_factor = 400 if len(tgt.exposures) > 3 else 300 # Build in a fudge factor based on # of exps
				tgt.total_minutes = int(round((sum(tgt.exposures.values()) + fudge_factor)/60)) # Sum total minutes
			
			good_airmass = tgt.raw_airmass_array[np.asarray(np.where(tgt.raw_airmass_array <= Constants.airmass_threshold))]
			integrated_good_am = np.sum(good_airmass)
			
			if integrated_good_am > 0:
				tgt.total_good_air_mass = integrated_good_am

			if tgt.total_observable_min > 0:
				tgt.fraction_time_obs = float(tgt.total_minutes)/float(tgt.total_observable_min)
				
	def swope_filter_row(self, exp_name, exp_time):
		filter_row = []
		filter_row.append(None)
		filter_row.append(None)
		filter_row.append(None)
		filter_row.append(None)
		filter_row.append(exp_name)
		filter_row.append(exp_time)
		
		return filter_row
		
	def write_schedule(self, observatory_name, obs_date, targets):
		
		file_to_write = "%s_%s_%s_GoodSchedule.csv" % (observatory_name, self.name, obs_date.strftime('%Y%m%d'))
		with open(file_to_write,"w") as csvoutput:
			writer = csv.writer(csvoutput, lineterminator="\n")

			output_rows = []
			header_row = []
			header_row.append("Object Name")
			header_row.append("Right Ascension")
			header_row.append("Declination")
			header_row.append("Estimated Magnitude")
			header_row.append("Filter")
			header_row.append("Exposure Time")
			output_rows.append(header_row)

			last_filter = Constants.r_band
			for t in targets:
				ra = t.coord.ra.hms
				dec = t.coord.dec.dms

				tgt_row = []
				tgt_row.append(t.name)
				tgt_row.append("=\"%02d:%02d:%0.1f\"" % (ra[0],ra[1],ra[2]))
				tgt_row.append("=\"%02d:%02d:%0.1f\"" % (dec[0],np.abs(dec[1]),np.abs(dec[2])))
				tgt_row.append(None)

				# Last criterion: if previous obj had full 6 filters, but this target only has 3
				if (last_filter == Constants.r_band) or \
				   (last_filter == Constants.i_band) or \
					(last_filter == Constants.g_band) or \
					(last_filter == Constants.B_band and len(t.exposures) < 6):

					tgt_row.append(Constants.r_band)
					tgt_row.append(10) # Acquisition in r
					output_rows.append(tgt_row)

					# Start in riguVB order
					if Constants.r_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.r_band, t.exposures[Constants.r_band]))

					if Constants.i_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.i_band, t.exposures[Constants.i_band]))
					
					if Constants.g_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.g_band, t.exposures[Constants.g_band]))
					
					last_filter = Constants.g_band

					if len(t.exposures) > 3:

						if Constants.u_band in t.exposures:
							output_rows.append(self.swope_filter_row(Constants.u_band, t.exposures[Constants.u_band]))

						if Constants.V_band in t.exposures:
							output_rows.append(self.swope_filter_row(Constants.V_band, t.exposures[Constants.V_band]))

						if Constants.B_band in t.exposures:
							output_rows.append(self.swope_filter_row(Constants.B_band, t.exposures[Constants.B_band]))

						last_filter = Constants.B_band
					#This last_filter business is now complicated... 
				# Flip order: BVugir
				else:
					tgt_row.append(Constants.B_band)
					tgt_row.append(20) # Acquisition in B
					output_rows.append(tgt_row)

					if Constants.B_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.B_band, t.exposures[Constants.B_band]))
					if Constants.V_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.V_band, t.exposures[Constants.V_band]))
					if Constants.u_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.u_band, t.exposures[Constants.u_band]))
					if Constants.g_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.g_band, t.exposures[Constants.g_band]))
					if Constants.i_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.i_band, t.exposures[Constants.i_band]))
					if Constants.r_band in t.exposures:
						output_rows.append(self.swope_filter_row(Constants.r_band, t.exposures[Constants.r_band]))
					
					last_filter = Constants.r_band
					
			writer.writerows(output_rows)


# Used with Lick Observatory
class Nickel(Telescope):
	
	def __init__(self):
		self.targets = None
		self.name = "Nickel"
		# Filter name: Zero-point
		self.filters = {
			Constants.B_band:22.58,
			Constants.V_band:22.88,
			Constants.r_prime:22.81,
			Constants.i_prime:22.65
		}
		self.exp_funcs = {
			TargetType.Supernova: self.compute_sn_exposure,
			TargetType.Template: self.compute_template_exposure,
			TargetType.Standard: self.compute_standard_exposure,
			TargetType.GW_Static: self.compute_GW_Static_exposure,
			TargetType.GW_Dynamic: self.compute_GW_Dynamic_exposure
		}
	
	def set_targets(self, targets):
		self.targets = targets
		
	def get_targets(self):
		return self.targets
	
	def compute_GW_Static_exposure(self, GW_Static):
		exposures = {}
		
		exp_time = 120 # default to 120 seconds

		if GW_Static.static_exp_time is not None:
			exp_time = GW_Static.static_exp_time
			
		exposures.update({Constants.B_band: exp_time})
		exposures.update({Constants.V_band: exp_time})
	
		GW_Static.exposures = exposures

	def compute_GW_Dynamic_exposure(self, GW_Dynamic):
		exposures = {}

		App_Mag = GW_Dynamic.est_abs_mag + 5.0*np.log10(GW_Dynamic.host_dist_mpc*1.e6) - 5.0

		#AbsMag is t[8], and Host_Dist t[9]
		#We need to compute App_Mag t[11] with above function, and assume a S_N value of 30:

		s_to_n = 30.

		B_exp = self.time_to_S_N(s_to_n, App_Mag, self.filters[Constants.B_band])
		V_exp = self.time_to_S_N(s_to_n, App_Mag, self.filters[Constants.V_band])

		exposures.update({Constants.B_band: B_exp})
		exposures.update({Constants.V_band: V_exp})

		GW_Dynamic.exposures = exposures


	def compute_sn_exposure(self, sn):
		exposures = {}
		
		# Compute the current guess at apparent magnitude
		days_from_disc = (sn.obs_date - sn.disc_date).days
		mag_reduction = days_from_disc*0.03
		adj_app_mag = sn.apparent_mag + mag_reduction

		# Change S/N depending on phase...
		s_to_n = 10 # base signal to noise
		if days_from_disc <= 10:
			s_to_n = 30
		elif days_from_disc > 10 and days_from_disc <= 60:
			s_to_n = 20
		
		exposures.update({Constants.r_prime: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.r_prime]))})
		exposures.update({Constants.i_prime: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.i_prime]))})

		# Only include these exposures if a relatively new SN
		if days_from_disc < 60:
			exposures.update({Constants.B_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.B_band]))})
			exposures.update({Constants.V_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, adj_app_mag, self.filters[Constants.V_band]))})
		
		# Finally, don't go less than 45s (~ readout time), don't go more than 600s on Swope
		for key, value in exposures.items():
			
			if exposures[key] < 45:
				exposures[key] = 45
			elif exposures[key] > 600:
				exposures[key] = 600
		
		sn.exposures = exposures
	
	def compute_standard_exposure(self, std):
		exposures = {}
		s_to_n = 100
		
		# Don't know what the apparent mag should be?
		exposures.update({Constants.r_prime: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.r_prime]))})
		exposures.update({Constants.i_prime: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.i_prime]))})
		exposures.update({Constants.B_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.B_band]))})
		exposures.update({Constants.V_band: self.round_to_num(Constants.round_to, self.time_to_S_N(s_to_n, std.ApparentMag, self.filters[Constants.V_band]))})
		
		# Finally, don't go less than 10s for Nickel std, don't go more than 600s on Nickel
		for key, value in exposures.items():
			
			if exposures[key] < 10:
				exposures[key] = 10
			elif exposures[key] > 600:
				exposures[key] = 600
		
		std.exposures = exposures
	
	def compute_template_exposure(self, tmp):
		exposures = {}
		exposures.update({Constants.B_band: 1800})
		exposures.update({Constants.V_band: 1200})
		exposures.update({Constants.r_prime: 1200})
		exposures.update({Constants.i_prime: 1200})
		
		tmp.exposures = exposures

	
	def compute_exposures(self):
		for tgt in self.targets:			
			
			total_possible_time = np.sum(np.where(tgt.raw_airmass_array <= Constants.airmass_threshold)[0])
			
			if total_possible_time > 0:
				tgt.total_observable_min = total_possible_time
				
				self.exp_funcs[tgt.type](tgt) # Sets exposures for each target by target type
				
				# per observatory - estimatation for Lick Nickel
				fudge_factor = 200 if len(tgt.exposures) > 2 else 100 # Build in a fudge factor based on # of exps
				tgt.total_minutes = round((sum(tgt.exposures.values()) + fudge_factor)/60) # Sum total minutes
			
			good_airmass = tgt.raw_airmass_array[np.asarray(np.where(tgt.raw_airmass_array <= Constants.airmass_threshold))]
			integrated_good_am = np.sum(good_airmass)
			if integrated_good_am > 0:
				tgt.total_good_air_mass = integrated_good_am

			if tgt.total_observable_min > 0:
				tgt.fraction_time_obs = float(tgt.total_minutes)/float(tgt.total_observable_min)

	def nickel_filter_row(self, exp_name, exp_time):
		filter_row = []
		filter_row.append(None)
		filter_row.append(None)
		filter_row.append(None)
		filter_row.append(None)
		filter_row.append(exp_name)
		filter_row.append(exp_time)
		
		return filter_row
				
	def write_schedule(self, observatory_name, obs_date, targets):		
		file_to_write = "%s_%s_%s_GoodSchedule.csv" % (observatory_name, self.name, obs_date.strftime('%Y%m%d'))
		with open(file_to_write,"w") as csvoutput:
			writer = csv.writer(csvoutput, lineterminator="\n")

			output_rows = []
			header_row = []
			header_row.append("Object Name")
			header_row.append("Right Ascension")
			header_row.append("Declination")
			header_row.append("Estimated Magnitude")
			header_row.append("Filter")
			header_row.append("Exposure Time")
			output_rows.append(header_row)

			last_filter = Constants.r_prime
			for t in targets:				
				ra = t.coord.ra.hms
				dec = t.coord.dec.dms

				tgt_row = []
				tgt_row.append(t.name)
				tgt_row.append("=\"%02d:%02d:%0.1f\"" % (ra[0],ra[1],ra[2]))
				tgt_row.append("=\"%02d:%02d:%0.1f\"" % (dec[0],np.abs(dec[1]),np.abs(dec[2])))
				tgt_row.append(None)

				# Last criterion: if previous obj had full 4 filters, but this target only has 2
				if (last_filter == Constants.r_prime) or \
				   (last_filter == Constants.i_prime) or \
					(last_filter == Constants.B_band and len(t.exposures) < 4):

					tgt_row.append(Constants.r_prime)
					tgt_row.append(10) # Acquisition in r'
					output_rows.append(tgt_row)

					# Start in r'i'VB order
					output_rows.append(self.nickel_filter_row(Constants.r_prime, t.exposures[Constants.r_prime]))
					output_rows.append(self.nickel_filter_row(Constants.i_prime, t.exposures[Constants.i_prime]))
					last_filter = Constants.i_prime
					
					if len(t.exposures) > 2:
						output_rows.append(self.nickel_filter_row(Constants.V_band, t.exposures[Constants.V_band]))
						output_rows.append(self.nickel_filter_row(Constants.B_band, t.exposures[Constants.B_band]))
						last_filter = Constants.B_band
					
				# Flip order: BVi'r'
				else:
					tgt_row.append(Constants.B_band)
					tgt_row.append(20) # Acquisition in B
					output_rows.append(tgt_row)

					output_rows.append(self.nickel_filter_row(Constants.B_band, t.exposures[Constants.B_band]))
					output_rows.append(self.nickel_filter_row(Constants.V_band, t.exposures[Constants.V_band]))
					output_rows.append(self.nickel_filter_row(Constants.i_prime, t.exposures[Constants.i_prime]))
					output_rows.append(self.nickel_filter_row(Constants.r_prime, t.exposures[Constants.r_prime]))
					last_filter = Constants.r_prime
					
			writer.writerows(output_rows)